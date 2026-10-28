# endstation

[![PyPI](https://img.shields.io/pypi/v/endstation?cacheSeconds=3600)](https://pypi.org/project/endstation/)
[![Python](https://img.shields.io/pypi/pyversions/endstation?cacheSeconds=3600)](https://pypi.org/project/endstation/)
[![tests](https://github.com/jamccoy/endstation/actions/workflows/test.yml/badge.svg)](https://github.com/jamccoy/endstation/actions/workflows/test.yml)
[![License: BSD-3-Clause](https://img.shields.io/badge/license-BSD--3--Clause-blue)](https://github.com/jamccoy/endstation/blob/master/LICENSE)

**[PyPI](https://pypi.org/project/endstation/)** · **[Changelog](https://github.com/jamccoy/endstation/blob/master/CHANGELOG.md)** · **[Issues](https://github.com/jamccoy/endstation/issues)**

endstation is a library of shared components for desktop scientific applications
written in Python. It provides the parts of such an application that surround the
analysis itself: guards for optional dependencies, progress reporting and
cancellation for slow work, collection of form errors, location of research data
kept outside the checkout, background workers for the user interface, embedded
figures, rendered documentation pages, and macOS application bundles.

The name is taken from synchrotron beamlines, where the endstation is the shared
apparatus to which each experiment is attached, such as the goniometer, detector and
motion control, as distinct from the science each experiment carries out.

## Why it exists

Four projects share the same structure: a Python science package with an optional
PySide6 and matplotlib front end, a macOS `.app`, research data held outside the
checkout, and a test suite that runs without a display. Each had solved those problems
separately, and the copies had diverged; a layout fix, a fix to worker shutdown and a
stronger test of the toolkit import had each been made in one project and not in the
others. This package now holds those components, so that a fix made once applies to
every project.

## The core has no dependencies

```toml
dependencies = []
```

One of the projects that depend on endstation, `eblfrac`, a fracturing tool for
electron-beam lithography patterns, declares exactly that, so its fracture engine and
GPF writer can be installed anywhere. A shared package that required numpy would remove
that property from every project that depends on it, and nothing would report the
change.

`endstation`, `endstation.optional`, `endstation.progress`, `endstation.forms` and
`endstation.paths` import no third-party packages, and
`tests/test_core_has_no_dependencies.py` fails if that changes. Everything that needs
more is installed through an extra:

| Subpackage | Extra | Needs |
|---|---|---|
| `endstation.qt` | `qt` | PySide6, matplotlib |
| `endstation.docs` | `docs` | matplotlib, for math only |
| `endstation.testing` | `testing` | pytest |
| `endstation.tools` | none | macOS `sips`/`iconutil` at runtime |

The package declares `requires-python = ">=3.10"`, because `eblfrac` declares 3.10 and
a shared package should not raise the minimum Python version of the projects that use
it.

## Install

```bash
pip install "endstation[qt]"
```

With [uv](https://docs.astral.sh/uv/), the same extras work:

```bash
uv pip install "endstation[qt]"    # into the active environment
uv add endstation                  # as a dependency of a uv project
```

Or from git, pinned to a tag:

```bash
pip install "endstation @ git+https://github.com/jamccoy/endstation.git@v0.2.6"
```

For working on endstation itself:

```bash
pip install -e '.[dev]'
```

### Publishing

`.github/workflows/publish.yml` releases to PyPI when a `v*` tag is pushed, using
Trusted Publishing, so no API token needs to be stored. The publisher is registered at
<https://pypi.org/manage/account/publishing/> for `jamccoy/endstation`, workflow
`publish.yml`, environment `pypi`.

## Contents

### `endstation.optional`: optional dependencies

```python
from endstation import require_extra, optional_module

require_extra("PySide6", "gui", still_works="The analysis works without it.")

astropy = optional_module("astropy", "trapezoid", package="als_eff_meas")
```

`require_extra` checks for the dependency with `find_spec`, so it costs nothing when the
dependency is present and can be called from a module that must not import a toolkit.
When the dependency is missing, the error names the extra that provides it and the
command that installs it. `optional_module` returns a lazy proxy, so a missing package
affects only the functions that use it and not the rest of the module.

The install command in the error message is quoted, because square brackets are glob
characters and zsh rejects an unquoted `pip install .[gui]` with `no matches found`.

### `endstation.progress`: progress reporting and cancellation

Progress is reported through a single callback, `progress(done, total)`. A callback
that needs to stop the work raises `Cancelled`, and the loops let the exception
propagate.

```python
from endstation.progress import cancelling, throttled

report = cancelling(throttled(on_progress), cancel_event.is_set)
```

A Python thread cannot be terminated from outside, and a NumPy call has no point at
which it can be interrupted, so the progress callback is the only place a caller can
stop the computation. Without it, a Cancel button would stop only the waiting, while
the computation continued and its result was discarded.

Progress reports are throttled, but the cancellation check runs at every call, so a
Cancel click takes effect at the next unit of work.

### `endstation.forms`: form validation

A form with several invalid fields reports all of them together, so that the user does
not have to correct them one at a time.

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

A missing data directory is reported with the name of the environment variable and the
path it resolved to. A bare `FileNotFoundError: [Errno 2]` on a path the user never
entered gives no indication of what to change.

### `endstation.testing`: headless test suites

The plugin is registered through the `pytest11` entry point, so no conftest needs to
load it. It sets `QT_QPA_PLATFORM=offscreen`, `QT_API`, `PYTEST_QT_API` and
`MPLBACKEND`, each with `setdefault`, so `QT_QPA_PLATFORM=cocoa pytest tests/test_gui.py`
still opens a real window. Setting `ENDSTATION_NO_HEADLESS=1` disables it.

## Tests

```bash
.venv/bin/python -m pytest -q
```

## The template

The same pyproject skeleton, CI workflow, headless conftest and ignore rules are also
repeated across these projects. They should not be a runtime dependency, so they are
provided as a [copier](https://copier.readthedocs.io) template instead:

```bash
pipx run copier copy gh:jamccoy/endstation my-project
```

The template asks whether the project has a PySide6 window and whether its tests read
data from outside the checkout. A library project receives no `gui/` directory, and its
CI does not install Qt system libraries it does not need.

The template also includes several details that are easy to overlook:

- A CI step that constructs a `QApplication` instead of only importing PySide6. The
  import succeeds before the platform plugin loads, and a missing system library only
  shows up when the plugin loads, so constructing the application makes the failure
  appear next to the installation step that caused it.
- A check that data-dependent tests were skipped rather than failed, and a minimum
  number of passing tests, so that a suite which loses tests without notice fails CI.
- No `qt_api` setting in `[tool.pytest.ini_options]`. It is a pytest-qt option, so
  setting it makes the suite fail on a machine without the toolkit; the plugin sets
  `PYTEST_QT_API` instead.
- Local working notes are ignored from the first commit, so a scratch file is not
  published by accident.

`tests/test_template.py` renders both variants of the template and checks the output,
so a Jinja error, or a `${{ }}` expression consumed by the renderer, fails in this
repository rather than in a newly generated project.
