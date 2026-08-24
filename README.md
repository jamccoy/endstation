# endstation

Shared scaffolding for desktop scientific applications.

Not a science library. This is the apparatus that surrounds an analysis:
guarding optional dependencies, reporting and cancelling slow work, collecting
form errors, locating research data that is deliberately not in the checkout,
running work off the UI thread, embedding a figure, rendering a documentation
page, and building a macOS bundle.

The name is the point. At a synchrotron the endstation is the shared apparatus
every experiment bolts onto — goniometer, detector, motion control — distinct
from the science each experiment does.

## Why it exists

Four projects were four independent builds of the same artifact: a Python
science package with an optional PySide6/matplotlib front-end, a hand-rolled
macOS `.app`, private research data held outside the checkout, and a test suite
that has to stay runnable headless. Every one of those concerns had been solved
three or four times, and the copies had already drifted:

- One project derives its layout floor from platform metrics after the
  hardcoded-width bug shipped twice unnoticed; two others still hardcode a
  pixel count.
- One worker fixed a slot-ordering bug and a garbage-collection crash during
  teardown; two others have neither fix.
- The test that keeps a toolkit out of the pure layer exists three times, and
  the strongest version — a subprocess import, which catches *transitive*
  imports — is in only one of them.

Each of those is a fix that landed in one place and not the others. That is the
problem this package exists to stop.

## The one rule

**The core has no dependencies.**

```toml
dependencies = []
```

`eblfrac` declares exactly that, so its fracture engine and GPF writer install
anywhere. A shared package that quietly pulled numpy in would take that away at
install time, from every downstream user, with no error to notice.

So `endstation`, `endstation.optional`, `endstation.progress`,
`endstation.forms` and `endstation.paths` import nothing third-party at all, and
`tests/test_core_has_no_dependencies.py` fails if that ever stops being true.
Everything heavier lives behind an extra:

| Subpackage | Extra | Needs |
|---|---|---|
| `endstation.qt` | `qt` | PySide6, matplotlib |
| `endstation.docs` | `docs` | matplotlib (math), markdown (HTML) |
| `endstation.testing` | `testing` | pytest |
| `endstation.tools` | — | macOS `sips`/`iconutil` at runtime |

`requires-python = ">=3.10"`, because `eblfrac` declares 3.10. A shared package
must not raise its consumers' floor.

## Install

```bash
pip install -e '.[dev]'
```

## What is in it

### `endstation.optional` — dependencies that explain themselves

```python
from endstation import require_extra, optional_module

require_extra("PySide6", "gui", still_works="The analysis works without it.")

astropy = optional_module("astropy", "trapezoid", package="als_eff_meas")
```

`require_extra` is a check that uses `find_spec`, so it costs nothing when the
dependency is present and is safe to call from a module forbidden to import a
toolkit. `optional_module` is a lazy proxy, so one missing package breaks only
the functions that actually need it rather than every function in the module.

The install command in the message is quoted, and the quotes are load-bearing:
square brackets are glob characters, and zsh answers an unquoted
`pip install .[gui]` with `no matches found`.

### `endstation.progress` — cancellation that actually stops the work

One callback, `progress(done, total)`. A callback that wants to stop raises
`Cancelled`, and the loops let it propagate.

```python
from endstation.progress import cancelling, throttled

report = cancelling(throttled(on_progress), cancel_event.is_set)
```

A Python thread cannot be killed and a NumPy-bound call has no check point, so
the progress callback is the only moment a caller gets to interrupt. Without it
cancelling stops the *waiting* — the CPU keeps working and the result is
computed and thrown away.

Reporting is throttled; the cancellation check is not. A Cancel click lands at
the next unit of work, not the next percent.

### `endstation.forms` — errors collected, not raised on the first failure

A form with three bad fields reports three problems, rather than making the user
fix them one at a time and rediscover the next on each attempt.

```python
errors = ErrorCollector()
if period <= 0:
    errors.add("period", "must be positive")
if not 0 <= trim < MAX_TRIM:
    errors.add("trim", f"must be between 0 and {MAX_TRIM}")
errors.raise_if_any()
```

### `endstation.paths` — data that is deliberately not in the checkout

```python
scans = find_data("GRATINGLAB_AFM_DIR", "~/Documents/afm_scans",
                  hint="docs/DATA.md")
```

A missing root is reported by name. `FileNotFoundError: [Errno 2]` on a path the
user never typed is unactionable; naming the variable and the resolved path
makes it a one-line fix.

### `endstation.testing` — a headless suite without the conftest preamble

Registered through the `pytest11` entry point, so no conftest has to name it. It
sets `QT_QPA_PLATFORM=offscreen`, `QT_API`, `PYTEST_QT_API` and `MPLBACKEND` —
all with `setdefault`, so `QT_QPA_PLATFORM=cocoa pytest tests/test_gui.py` still
opens a real window. `ENDSTATION_NO_HEADLESS=1` disables it entirely.

## Tests

```bash
.venv/bin/python -m pytest -q
```

## The template

The pyproject skeleton, the CI workflow, the headless conftest and the ignore
rules are duplicated across these projects too — but they must not become a
runtime dependency, so they live in a [copier](https://copier.readthedocs.io)
template rather than in the package:

```bash
pipx run copier copy gh:jamccoy/endstation my-project
```

It asks whether the project has a PySide6 window and whether its tests read data
held outside the checkout, and renders accordingly — a library project gets no
`gui/` directory, and no apt step installing Qt system libraries into a CI run
that will never open a window.

What it carries that is easy to get wrong:

- The CI step that **constructs a `QApplication`** rather than merely importing
  PySide6. The import succeeds long before the platform plugin is asked to load,
  which is where a missing system library actually bites — and it fails next to
  the apt step that would be at fault.
- The check that data-dependent tests **skipped rather than failed**, and the
  floor on how many tests must pass. A suite that quietly shrinks goes green
  while testing almost nothing.
- No `qt_api` in `[tool.pytest.ini_options]`. It is a pytest-qt option, so
  declaring it makes the suite unrunnable without the toolkit — the plugin
  exports `PYTEST_QT_API` instead.
- Local working notes ignored from the first commit, as a category, so a
  scratch file never lands in a published repository by accident.

`tests/test_template.py` renders both variants and inspects the output, so a
Jinja typo or a `${{ }}` the renderer ate fails here rather than the next time
someone starts a project.
