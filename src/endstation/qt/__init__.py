"""The widget layer: the only part of a project allowed to import a toolkit.

The boundary is enforced at the package level instead of by convention, so that
a test can check it (see :mod:`endstation.testing.boundary`). The drift it
prevents is of the ordinary kind: someone needs a single QColor in a module
that was pure, and the headless tests quietly become impossible to run.

Two rules accompany this package, and both were learned through failures in
every project it was drawn from.

1. Only this subpackage may import a Qt binding. Everything that can be
   decided without a window (parsing, validation, which orders to draw, what
   the provenance panel says) belongs outside it, where it is tested without
   a display. Widget code is the least testable part of any project, and the
   value of a scientific application lies in defensible numbers. Keeping the
   logic out means that a bug in the untested layer can produce a wrong layout
   but never a wrong number.

2. Only the main thread may touch a matplotlib figure. A worker returns
   plain data (arrays, dataclasses, dictionaries) and the window draws from
   it. Drawing from a worker is a well-known cause of crashes in Qt + matplotlib
   applications, which usually occur intermittently and far from the cause.

Importing this subpackage requires PySide6 and matplotlib, which are optional
extras::

    pip install -e '.[qt]'
"""

from __future__ import annotations

import os

from ..optional import missing_extra_message, require_extra

__all__ = [
    "QT_MISSING_MESSAGE",
    "STILL_WORKS",
    "require_qt",
    "use_qt_backend",
]

#: What a missing toolkit does *not* break. Without a sentence like this, a
#: user who only wanted the analysis reads an absent GUI extra as a broken
#: install.
STILL_WORKS = "Everything that is not the window works without it."

#: The default message, for the common case: a project whose GUI extra is named
#: ``gui``. Downstream suites assert on this, so it is a module constant rather
#: than something only reachable by triggering the failure.
QT_MISSING_MESSAGE = missing_extra_message("PySide6", "gui", still_works=STILL_WORKS)

# matplotlib's Qt shim (backends/qt_compat.py) picks a binding from sys.modules
# first and QT_API second. Without this, a stray PyQt5 in the environment wins
# and its canvas refuses to parent into a PySide6 window -- a realistic thing to
# find installed, since more than one project here shipped PyQt5 until recently.
#
# At module scope, and before anything below imports matplotlib, because the
# shim reads it once.
os.environ.setdefault("QT_API", "PySide6")


def require_qt(package: str | None = None, *, extra: str = "gui") -> None:
    """Raise an informative error instead of a bare ImportError.

    Call this from a console-script entry point before importing the window,
    so that the entry point can live in a toolkit-free module and a missing
    extra produces an install instruction instead of a traceback naming a
    package the user never asked for.

    ``extra`` defaults to ``"gui"`` because every downstream project uses that
    name. This package's own extra is ``qt``, since here the toolkit is the
    subject of the package and not its interface, and it must be passed
    explicitly in that case. A message naming an extra that does not exist is
    worse than no message.

    The function uses ``find_spec`` instead of an import, so it is safe to call
    from outside this subpackage. This is necessary because the module that
    owns the entry point is usually one the boundary test forbids from
    importing Qt.
    """
    require_extra("PySide6", extra, package=package, still_works=STILL_WORKS)


def use_qt_backend(*, force: bool = False) -> None:
    """Pin matplotlib to Qt before any figure or canvas is created.

    Without this the application inherits the platform default, which on macOS
    is ``macosx``: a second native GUI toolkit, with its own event loop, in a
    process already running Qt's. matplotlib does auto-select a Qt backend once
    a binding is imported, but only if nothing has already bound one, and an
    application cannot guarantee that about its own import order.

    The call does nothing when a Qt backend is already active, so calling it
    twice is safe.

    ``force`` decides what happens under Agg, and each setting is correct for a
    different caller. By default an explicit ``MPLBACKEND=Agg`` (which the
    headless test plugin sets) is left alone and is not overridden into a
    window nobody can see. That is the right behaviour for a library, since a
    suite that requested Agg intended to get it.

    It is the wrong behaviour for an application that wants a real Qt backend
    even under test, so that its tests exercise the configuration it ships and
    not one they constructed by calling ``matplotlib.use("QtAgg")`` themselves.
    ``eblfrac`` needed exactly that and kept a forked copy of this function to
    get it, with a docstring explaining that the two requirements are opposite
    and that the copy therefore stays local. The requirements are opposite, but
    they are compatible. This keyword allows one function to serve both, and it
    allows that fork to be removed.
    """
    require_extra(
        "matplotlib",
        "qt",
        still_works="Everything that does not draw works without it.",
    )
    import matplotlib

    current = matplotlib.get_backend().lower()
    if "qt" in current:
        return
    if current == "agg" and not force:
        return
    matplotlib.use("QtAgg")
