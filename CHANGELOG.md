# Changelog

Notable changes, newest first. This project is pre-1.0 and four projects depend
on it, so the main purpose of this file is to record each breaking change before a
dependent project encounters it. Until 1.0, a minor version may change an
interface, but every such change is listed here.

Format loosely follows [Keep a Changelog](https://keepachangelog.com).
Versions are read from `endstation.__version__`.

## Unreleased

### Added

- `endstation.qt.gc_guard`, which keeps Python's cycle collector on the GUI
  thread. While an object holds the guard, automatic collection is off and a
  timer on the GUI thread collects whenever the generation counts say a
  collection is due; the last holder's `destroyed` signal turns automatic
  collection back on, and an `atexit` hook does the same for a holder that is
  never deleted. Without it the collector runs on whichever thread allocates
  past its threshold, which is often a worker, and freeing a Qt object there
  segfaulted gratinglab on macOS; the exit hook prevents the `bool_dealloc`
  abort that Python's final collection caused after Qt was gone. It is
  gratinglab's `gratinglab.gui.qt.gc_guard` with unchanged behaviour, so
  gratinglab can import it from here instead. It is opt-in because it turns
  automatic collection off for the whole process: call `guard(window)` from a
  main window's constructor, or pass `gc_guard=True` to `JobRunner`.
- `JobRunner(stack_size=..., gc_guard=False)` keywords, and a read-only
  `JobRunner.stack_size`.

### Fixed

- `JobRunner`'s worker thread now has an 8 MiB stack
  (`endstation.qt.jobs.DEFAULT_STACK_BYTES`) instead of the platform's default
  for secondary threads, which is 512 KiB on macOS. LAPACK's dense complex
  solve overruns the smaller stack, so `np.linalg.solve` on a matrix a few
  hundred rows square inside a job crashed the process, as it did in
  gratinglab. `stack_size=None` restores the platform default.

## 0.2.5

### Fixed

- The `qt` and `dev` extras no longer install PySide6 6.12.0 below Python
  3.12. That release aborts the interpreter at exit (`Fatal Python error:
  bool_dealloc`) after heavy GUI use, because it releases a reference to
  `True` or `False` that it does not own; on 3.12 and later those objects are
  immortal and the bug is harmless. Only 6.12.0 is excluded, so a fixed
  release is taken as soon as it exists.

## 0.2.4

### Changed

- The README, which is the PyPI page, the changelog and every docstring are
  rewritten in plain prose, without slogan headings, closing aphorisms or
  emphasis. No code or interface changed: each module's syntax tree with its
  docstrings blanked is identical to 0.2.3's.
- A test holds the README's install-from-git pin to `__version__`, so a
  release commit that forgets to move it fails CI instead of publishing a
  README that pins the previous release.

### Fixed

- The `endstation.testing.boundary` module docstring named `assert_qt_free`
  as the general form of the import check. The general form is
  `assert_import_free`, which takes the forbidden names; `assert_qt_free` is
  that check with the Qt bindings filled in.

## 0.2.3

### Changed

- The README shows how to install with uv (`uv pip install` and `uv add`),
  so PyPI's project page does too. No code changes.

## 0.2.2

### Fixed

- `endstation-publish-wiki` works on Windows. It read and wrote pages in the
  locale encoding, cp1252 there, and failed on the first UTF-8 page with
  `UnicodeDecodeError: 'charmap' codec can't decode byte 0x81`. Pages are now
  read as UTF-8, a page saved in cp1252 is accepted rather than refused, and
  everything is written as UTF-8.
- `endstation.testing.boundary` decodes its probe interpreter's output as UTF-8
  and tells the probe to write UTF-8, so it no longer raises `EncodingWarning`
  in a suite that turns warnings into errors.
- `endstation-app` writes its launcher stub as UTF-8 and reads it back
  leniently in `check_app`.

### Changed

- CI runs the suite on Windows as well, and every test run sets
  `PYTHONWARNDEFAULTENCODING=1`, so a text read or write with no encoding fails
  on every OS rather than only where the default is not UTF-8.
- Coverage leaves out `make_app.py` except on macOS, the only platform where
  its tests run. Off macOS it held the total at 73% against the 78% floor, so
  CI had been red on Linux since 0.2.0. The floor is unchanged.

## 0.2.1

### Changed

- The README, which is the PyPI page, is rewritten in plainer prose: no em
  dashes, and the install, publishing and template notes say what they do
  without the pitch. The docstrings lose their bold paragraph leads and a few
  stock phrases. No code or interface changed.

## 0.2.0

First release on PyPI. 0.1.0 was tagged but never published, because the tag
predates `publish.yml`, so `pip install endstation` starts here.

### Added

- `use_qt_backend(force=False)`. With `force=True` the Qt backend is selected
  even when matplotlib is already on Agg. The default is unchanged and still
  leaves an explicit `MPLBACKEND=Agg` alone.

  Both behaviours are correct for different callers, so the choice is a keyword
  argument. A library should respect a test suite that asked for Agg, whereas
  an application may want its tests to exercise the backend it ships with.
  `eblfrac` needed the second behaviour and kept a forked copy of this function
  to obtain it; that copy can now be removed.

- Coverage measurement (`pytest-cov` in `dev`, `[tool.coverage]` in
  `pyproject.toml`), with a ratchet floor rather than a target.

- `PyYAML` declared in the `dev` extra. It was reaching the environment only as
  a transitive dependency of `copier`, while `tests/test_packaging.py`
  bare-imports it.

### Changed

- CI measures coverage with `coverage run -m pytest` instead of `pytest --cov`.
  The two disagree by 8 points of total coverage for this package in particular.
  pytest imports `pytest11` entry-point plugins before its own conftest (which
  is why `endstation.testing.plugin` is written as a plugin), and that plugin
  imports the entire dependency-free core. Under `--cov` all of it is imported
  before coverage starts recording, so `forms.py` reported 31% when it is 88%
  covered and `plugin.py` reported 0%. Downstream suites that adopt coverage
  will hit the same thing.

- The CI "did the suite quietly shrink" gate no longer counts passing tests. A
  floor of 130 against a suite of 186 tolerated a 30% collapse, and it had to be
  raised by hand whenever the suite grew, so in practice it only fell further
  behind. It now asserts directly on the condition that number stood for: no
  test is skipped with `"the qt extra is not installed"` in a job that installs
  the toolkit.
  A low absolute floor remains as a backstop against total collection failure.

- Every CI step containing a `python - <<'PY'` heredoc declares `shell: bash`.
  Groundwork for a `windows-latest` leg: PowerShell is that runner's default
  shell and cannot parse a heredoc, and the resulting error names neither.
  `tests/test_packaging.py` now asserts this, because otherwise the failure
  would appear only on the newly added leg and could be mistaken for a general
  Windows problem.

### Fixed

- Three wrong statements in the documentation, two of them in the front-page
  docstring: the extras table named a `test` extra that does not exist (it is
  `testing`), and claimed `endstation.docs` needs the `markdown` package, which
  `docs/markdown.py` is deliberately written without. `copier.yml` documented a
  `gh:jamccoy/endstation-template` repository that does not exist.

  A message naming an extra that does not exist is the kind of error
  `endstation.optional` was written to prevent.

## 0.1.0

First release. Extracted from `gratinglab`, `afm_blaze_meas`, `eblfrac` and
`als_eff_meas`, each of which had independently built the same apparatus:
optional-dependency guards, cancellable workers, a Qt/matplotlib pane, private
data roots outside the checkout, a headless test suite, and a macOS `.app`.

The core declares `dependencies = []` and CI enforces it on a bare interpreter.
Everything heavier lives behind the `qt`, `mpl`, `docs` and `testing` extras.
