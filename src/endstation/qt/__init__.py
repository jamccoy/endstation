"""The widget layer: the only part of a project allowed to import a toolkit.

That boundary is a *package* boundary rather than a convention, precisely so a
test can enforce it -- see :mod:`endstation.testing.boundary`. The drift it
prevents is the ordinary kind: someone needing "just a QColor" in a module that
was pure, and the headless tests quietly becoming un-runnable.

Two rules travel with this package, and both were learned the hard way in every
project it was drawn from:

1. **Only this subpackage may import a Qt binding.** Everything that can be
   decided without a window -- parsing, validation, which orders to draw, what
   the provenance panel says -- belongs outside it, where it is tested without
   a display. Widget code is the least testable part of any project, and the
   value of a scientific application is defensible numbers; keeping the logic
   out means a bug in the untested layer produces a wrong *layout*, never a
   wrong *number*.

2. **Only the main thread may touch a matplotlib figure.** A worker returns
   plain data -- arrays, dataclasses, dictionaries -- and the window draws from
   it. Drawing from a worker is the classic way a Qt + matplotlib application
   crashes, usually intermittently and far from the cause.

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
    """Raise something useful rather than a bare ImportError.

    Call this from a console-script entry point *before* importing the window,
    so the entry point can live in a toolkit-free module and a missing extra
    produces an install instruction instead of a traceback naming a package the
    user never asked for.

    ``extra`` defaults to ``"gui"`` because that is what every project
    downstream calls it. This package's own is ``qt``, since here the toolkit is
    the subject rather than the interface -- pass it explicitly in that case. A
    message naming an extra that does not exist is worse than no message.

    Uses ``find_spec`` rather than an import, so it is safe to call from outside
    this subpackage -- which is the point, since the module that owns the entry
    point is usually one the boundary test forbids from importing Qt.
    """
    require_extra("PySide6", extra, package=package, still_works=STILL_WORKS)


def use_qt_backend() -> None:
    """Pin matplotlib to Qt before any figure or canvas is created.

    Without this the application inherits the platform default, which on macOS
    is ``macosx`` -- a second native GUI toolkit, with its own event loop, in a
    process already running Qt's. matplotlib does auto-select a Qt backend once
    a binding is imported, but only if nothing has already bound one, and
    "nothing has already bound one" is not something an application can promise
    about its own import order.

    A no-op when a Qt backend is already active, so calling it twice is safe and
    so an explicit ``MPLBACKEND=Agg`` -- which is what the headless test plugin
    sets -- is left alone rather than being overridden into a window nobody can
    see.
    """
    import matplotlib

    current = matplotlib.get_backend().lower()
    if "qt" in current or current == "agg":
        return
    matplotlib.use("QtAgg")
