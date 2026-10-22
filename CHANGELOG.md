# Changelog

Notable changes, newest first. This project is pre-1.0 and four projects depend
on it, so the point of this file is narrower than a release note: **it is where
a breaking change is stated before it is discovered.** Until 1.0, a minor
version may break an interface; what it may not do is break one silently.

Format loosely follows [Keep a Changelog](https://keepachangelog.com).
Versions are read from `endstation.__version__`.

## Unreleased

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

  Both answers are correct for different callers, which is why this is a keyword
  rather than a fix. A library respects a suite that asked for Agg; an
  application that wants its tests to exercise the backend it actually ships
  does not. `eblfrac` needed the second and kept a forked copy of this function
  to get it — that fork can now go.

- Coverage measurement (`pytest-cov` in `dev`, `[tool.coverage]` in
  `pyproject.toml`), with a ratchet floor rather than a target.

- `PyYAML` declared in the `dev` extra. It was reaching the environment only as
  a transitive dependency of `copier`, while `tests/test_packaging.py`
  bare-imports it.

### Changed

- **CI measures coverage with `coverage run -m pytest`, not `pytest --cov`.**
  The two disagree by 8 points of total coverage for this package specifically.
  pytest imports `pytest11` entry-point plugins before its own conftest — which
  is the whole reason `endstation.testing.plugin` is a plugin — and that plugin
  imports the entire dependency-free core. Under `--cov` all of it is imported
  before coverage starts recording, so `forms.py` reported 31% when it is 88%
  covered and `plugin.py` reported 0%. Downstream suites that adopt coverage
  will hit the same thing.

- The CI "did the suite quietly shrink" gate no longer counts passing tests. A
  floor of 130 against a suite of 186 tolerated a 30% collapse, and it needed
  raising by hand whenever the suite grew, so it only ever rotted downward. It
  now asserts directly on what that number was reaching for: no test skipped
  with `"the qt extra is not installed"` in a job that installs the toolkit.
  A low absolute floor remains as a backstop against total collection failure.

- Every CI step containing a `python - <<'PY'` heredoc declares `shell: bash`.
  Groundwork for a `windows-latest` leg: PowerShell is that runner's default
  shell and cannot parse a heredoc, failing with an error that names neither.
  `tests/test_packaging.py` now asserts this, because the failure would
  otherwise appear only on the leg added last and read as "Windows is broken."

### Fixed

- Three wrong statements in the documentation, two of them in the front-page
  docstring: the extras table named a `test` extra that does not exist (it is
  `testing`), and claimed `endstation.docs` needs the `markdown` package, which
  `docs/markdown.py` is deliberately written without. `copier.yml` documented a
  `gh:jamccoy/endstation-template` repository that does not exist.

  A message naming an extra that does not exist is the exact failure
  `endstation.optional` was written to replace.

## 0.1.0

First release. Extracted from `gratinglab`, `afm_blaze_meas`, `eblfrac` and
`als_eff_meas`, each of which had independently built the same apparatus:
optional-dependency guards, cancellable workers, a Qt/matplotlib pane, private
data roots outside the checkout, a headless test suite, and a macOS `.app`.

The core declares `dependencies = []` and CI enforces it on a bare interpreter.
Everything heavier lives behind the `qt`, `mpl`, `docs` and `testing` extras.
