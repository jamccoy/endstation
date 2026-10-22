# endstation

[![PyPI](https://img.shields.io/pypi/v/endstation)](https://pypi.org/project/endstation/)
[![Python](https://img.shields.io/pypi/pyversions/endstation)](https://pypi.org/project/endstation/)
[![tests](https://github.com/jamccoy/endstation/actions/workflows/test.yml/badge.svg)](https://github.com/jamccoy/endstation/actions/workflows/test.yml)
[![License: BSD-3-Clause](https://img.shields.io/badge/license-BSD--3--Clause-blue)](https://github.com/jamccoy/endstation/blob/master/LICENSE)

**[PyPI](https://pypi.org/project/endstation/)** · **[Changelog](https://github.com/jamccoy/endstation/blob/master/CHANGELOG.md)** · **[Issues](https://github.com/jamccoy/endstation/issues)**

Shared scaffolding for desktop scientific applications.

It is not a science library. It covers what surrounds an analysis: guarding
optional dependencies, reporting and cancelling slow work, collecting form
errors, locating research data kept outside the checkout, running work off the
UI thread, embedding a figure, rendering a documentation page, and building a
macOS bundle.

At a synchrotron, the endstation is the shared apparatus that every experiment
bolts onto (goniometer, detector, motion control), as distinct from the science
each experiment does. That is where the name comes from.

## Why it exists

Four projects are the same kind of thing: a Python science package with
an optional PySide6/matplotlib front end, a macOS `.app`, research data held
outside the checkout, and a test suite that runs headless. Each had solved those
problems separately, and the copies had drifted. A layout fix, a worker teardown
fix and a stronger toolkit-import test had each landed in one project and not
the others. This package is where those pieces live now, so a fix lands once.

## The core has no dependencies

```toml
dependencies = []
```

`eblfrac` declares exactly that, so its fracture engine and GPF writer install
anywhere. A shared package that pulled in numpy would take that away from every
downstream user, with no error to notice.

`endstation`, `endstation.optional`, `endstation.progress`, `endstation.forms`
and `endstation.paths` import nothing third-party, and
`tests/test_core_has_no_dependencies.py` fails if that changes. Everything
heavier sits behind an extra:

| Subpackage | Extra | Needs |
|---|---|---|
| `endstation.qt` | `qt` | PySide6, matplotlib |
| `endstation.docs` | `docs` | matplotlib, for math only |
| `endstation.testing` | `testing` | pytest |
| `endstation.tools` | none | macOS `sips`/`iconutil` at runtime |

`requires-python = ">=3.10"`, because `eblfrac` declares 3.10 and a shared
package should not raise its consumers' floor.

## Install

```bash
pip install "endstation[qt]"
```

Or from git, pinned to a tag:

```bash
pip install "endstation @ git+https://github.com/jamccoy/endstation.git@v0.2.1"
```

For working on endstation itself:

```bash
pip install -e '.[dev]'
```

### Publishing

`.github/workflows/publish.yml` releases to PyPI when a `v*` tag is pushed,
using Trusted Publishing, so no API token is stored anywhere. The publisher is
registered at <https://pypi.org/manage/account/publishing/> for
`jamccoy/endstation`, workflow `publish.yml`, environment `pypi`.

## What is in it

### `endstation.optional`: dependencies that explain themselves

```python
from endstation import require_extra, optional_module

require_extra("PySide6", "gui", still_works="The analysis works without it.")

astropy = optional_module("astropy", "trapezoid", package="als_eff_meas")
```

`require_extra` checks with `find_spec`, so it costs nothing when the dependency
is present and is safe to call from a module that must not import a toolkit.
`optional_module` is a lazy proxy: a missing package breaks only the functions
that use it, not every function in the module.

The install command in the error message is quoted, because square brackets are
glob characters and zsh answers an unquoted `pip install .[gui]` with
`no matches found`.

### `endstation.progress`: cancellation that stops the work

One callback, `progress(done, total)`. A callback that wants to stop raises
`Cancelled`, and the loops let it propagate.

```python
from endstation.progress import cancelling, throttled

report = cancelling(throttled(on_progress), cancel_event.is_set)
```

A Python thread cannot be killed, and a NumPy call has no check point, so the
progress callback is the only place a caller can interrupt. Without it, cancel
only stops the waiting: the CPU keeps going and the result is thrown away.

Reporting is throttled; the cancellation check is not. A Cancel click takes
effect at the next unit of work, not the next percent.

### `endstation.forms`: every error at once

A form with three bad fields reports all three, instead of making the user fix
them one at a time.

```python
errors = ErrorCollector()
if period <= 0:
    errors.add("period", "must be positive")
if not 0 <= trim < MAX_TRIM:
    errors.add("trim", f"must be between 0 and {MAX_TRIM}")
errors.raise_if_any()
```

### `endstation.paths`: data kept outside the checkout

```python
scans = find_data("GRATINGLAB_AFM_DIR", "~/Documents/afm_scans",
                  hint="docs/DATA.md")
```

A missing root is reported by name. `FileNotFoundError: [Errno 2]` on a path the
user never typed tells them nothing; naming the variable and the resolved path
makes it a one-line fix.

### `endstation.testing`: a headless test suite with no conftest

It registers through the `pytest11` entry point, so no conftest has to name it.
It sets `QT_QPA_PLATFORM=offscreen`, `QT_API`, `PYTEST_QT_API` and `MPLBACKEND`,
each with `setdefault`, so `QT_QPA_PLATFORM=cocoa pytest tests/test_gui.py`
still opens a real window. `ENDSTATION_NO_HEADLESS=1` turns it off.

## Tests

```bash
.venv/bin/python -m pytest -q
```

## The template

The pyproject skeleton, CI workflow, headless conftest and ignore rules repeat
across these projects too. They should not be a runtime dependency, so they are
a [copier](https://copier.readthedocs.io) template instead:

```bash
pipx run copier copy gh:jamccoy/endstation my-project
```

It asks whether the project has a PySide6 window and whether its tests read data
from outside the checkout. A library project gets no `gui/` directory, and its
CI does not install Qt system libraries it will never use.

The template also carries a few things that are easy to miss:

- A CI step that constructs a `QApplication` instead of only importing PySide6.
  The import succeeds before the platform plugin loads, and the plugin is where
  a missing system library shows up, so the failure appears next to the apt
  step that caused it.
- A check that data-dependent tests were skipped rather than failed, and a
  minimum number of passing tests, so a suite that quietly shrinks does not go
  green.
- No `qt_api` in `[tool.pytest.ini_options]`. It is a pytest-qt option, so
  setting it makes the suite fail without the toolkit; the plugin exports
  `PYTEST_QT_API` instead.
- Local working notes are ignored from the first commit, so a scratch file does
  not end up in a published repository.

`tests/test_template.py` renders both variants and checks the output, so a
Jinja typo or a `${{ }}` the renderer ate fails here instead of in someone's
new project.
