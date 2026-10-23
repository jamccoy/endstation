"""A pytest plugin that makes a GUI test suite runnable headlessly.

Every project this was drawn from opens its ``tests/conftest.py`` with the same
preamble, for the same reasons, with the same justification in the comments.
This module is that preamble, registered through the ``pytest11`` entry point so
that it runs without any conftest naming it.

The main difficulty is timing, and it is the reason this is a plugin and not a
fixture. Both settings bind at first import: Qt reads ``QT_QPA_PLATFORM``
when the platform plugin loads, and matplotlib picks its backend when
``pyplot`` is first imported. A root ``conftest.py`` is imported before
``pytest_configure`` runs, so anything that waits for a hook is already too
late for a conftest with a module-level ``import matplotlib.pyplot``.
Entry-point plugins are imported earlier than any conftest, so the work is
deliberately done here at module scope.

The plugin sets ``MPLBACKEND`` instead of calling ``matplotlib.use("Agg")``.
The environment variable has the same effect at no cost, whereas calling
``use()`` would mean importing matplotlib inside a plugin that has to stay
importable in a project which has never installed it.

Every setting uses ``setdefault`` and none uses assignment, so ``QT_QPA_PLATFORM=cocoa
pytest tests/test_gui.py`` still opens a real window, which is the fastest way
to debug a layout problem. A plugin that removed that
option would be worse than the four copies it replaces.

Set ``ENDSTATION_NO_HEADLESS=1`` to disable all of it. This is intended for a
project that is installed alongside this one but does not want its behaviour.
"""

from __future__ import annotations

import os

import pytest

from ..paths import data_root

__all__ = ["data_dir_fixture", "skip_without_data"]


def _configure_headless() -> None:
    """Set the display and backend defaults, at import time. See the module docstring."""
    if os.environ.get("ENDSTATION_NO_HEADLESS"):
        return

    # Qt needs a platform plugin; there is no display on a CI runner, so render
    # off-screen rather than skipping the GUI suite entirely.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    # matplotlib's Qt shim (backends/qt_compat.py) picks a binding from
    # sys.modules first and QT_API second. Without this, a stray PyQt5 in the
    # environment wins and its canvas refuses to parent into a PySide6 window.
    os.environ.setdefault("QT_API", "PySide6")

    # pytest-qt probes every binding it knows unless told which to use. The
    # env var rather than the `qt_api` ini option, because that option is only
    # defined when pytest-qt is installed -- and a project whose suite declares
    # it then cannot run at all without the toolkit, which is exactly the
    # coupling the optional-extra design exists to avoid.
    os.environ.setdefault("PYTEST_QT_API", "pyside6")

    # Equivalent to matplotlib.use("Agg"), without importing matplotlib.
    os.environ.setdefault("MPLBACKEND", "Agg")


_configure_headless()


def skip_without_data(
    env_var: str,
    default: str,
    *,
    subpath: str | None = None,
):
    """Return the data directory, or skip the test naming the variable that enables it.

    The skip message has to name ``env_var``. A suite that skips silently looks
    identical to one that has no tests, and "20 skipped" with no explanation
    allows a green CI run to carry no information. The reason shown to a
    contributor without the research data is therefore the exact variable they
    would set to change it.

    Use through the :func:`data_dir` fixture factory, or directly::

        scans = skip_without_data("GRATINGLAB_AFM_DIR", "~/Documents/afm_scans")
    """
    root = data_root(env_var, default)
    target = root / subpath if subpath else root
    if not target.is_dir():
        pytest.skip(f"{target} not found; set {env_var} to enable this test")
    return target


def data_dir_fixture(
    env_var: str,
    default: str,
    *,
    subpath: str | None = None,
    scope: str = "session",
):
    """Build a fixture that yields a data directory or skips.

    Assign the result in a conftest::

        ref_dir = data_dir_fixture("GRATINGLAB_REF_DIR", "~/Documents/pcgrate")

    This is a factory and not a fixture because the variable name and default
    differ per project, and a fixture cannot be parameterised at definition time.
    """

    @pytest.fixture(scope=scope)
    def _fixture():
        return skip_without_data(env_var, default, subpath=subpath)

    return _fixture

