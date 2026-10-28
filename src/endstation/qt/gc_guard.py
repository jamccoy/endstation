"""Run Python's cycle collector on the GUI thread, never on a worker's.

Python's automatic collector runs on whichever thread happens to allocate past
its threshold. In an application that does its heavy work on a worker thread,
that is regularly the worker, and when the garbage it finds holds Qt objects (a
closed window, a figure from an earlier preview) it destroys them off the GUI
thread. Qt does not allow that, and on macOS it segfaults. gratinglab's CI died
that way, with ``Fatal Python error: Segmentation fault`` and
"Garbage-collecting" at the top of the worker thread's stack, in the middle of
an ordinary ``genfromtxt``. The same thing can happen to a user: close some
windows, press Run, and the application crashes.

The remedy is the usual one for PySide and PyQt applications. While any object
holds the guard, automatic collection is off, and a timer on the GUI thread
runs the collector whenever the generation counts say it is due, so garbage is
still collected promptly and always on the one thread allowed to free a Qt
object. When the last holder is destroyed, automatic collection is restored,
so code that runs with no window open behaves exactly as before.

A window that is closed but never deleted never releases the guard, so it also
restores collection at interpreter exit, through ``atexit``, and collects once
while Qt still exists. Without that, Python's own final collection freed the
accumulated Qt garbage after Qt was gone, and the process aborted at exit with
``Fatal Python error: bool_dealloc``.

The guard is opt-in because it changes a global setting: while it is held,
``gc.isenabled()`` is false for the whole process, including for code that has
nothing to do with Qt. Use it in an application whose windows or figures can
become garbage while a worker thread runs Python code, which is any window that
starts a :class:`~endstation.qt.jobs.JobRunner`. Call :func:`guard` from each
main window's constructor, or pass ``gc_guard=True`` to the runner, which holds
the guard for the runner's own lifetime. A test suite or a script with no
windows does not need it.
"""

from __future__ import annotations

import atexit
import gc

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

__all__ = ["INTERVAL_MS", "guard", "is_active"]

#: How often the GUI thread checks whether a collection is due. Checking is
#: three integer comparisons; collecting happens only past the thresholds.
INTERVAL_MS = 500

_collector: "_Collector | None" = None
_holders = 0


class _Collector(QObject):
    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.collect_if_due)
        self._timer.start(INTERVAL_MS)

    def collect_if_due(self) -> None:
        """What the automatic collector would have done, on this thread."""
        count0, count1, count2 = gc.get_count()
        limit0, limit1, limit2 = gc.get_threshold()
        if count0 > limit0:
            generation = 2 if count2 > limit2 else 1 if count1 > limit1 else 0
            gc.collect(generation)


def guard(holder: QObject) -> None:
    """Keep the collector on the GUI thread for as long as ``holder`` exists.

    Call this on the GUI thread, usually from a window's constructor. Each call
    is released by that object's ``destroyed`` signal, and the last release
    restores automatic collection. Calls from several windows nest.
    """
    global _collector, _holders
    if _holders == 0:
        app = QApplication.instance()
        # Whatever garbage already exists is collected here and now, on this
        # thread, before any worker can start allocating.
        gc.collect()
        gc.disable()
        _collector = _Collector(app if app is not None else holder)
    _holders += 1
    holder.destroyed.connect(_release)


def _release(*_args) -> None:
    global _collector, _holders
    _holders = max(0, _holders - 1)
    if _holders == 0 and _collector is not None:
        _collector._timer.stop()
        _collector.deleteLater()
        _collector = None
        gc.enable()


@atexit.register
def _restore_at_exit() -> None:
    """Collect while Qt is still alive, and hand collection back to Python."""
    if _holders > 0:
        gc.enable()
        gc.collect()


def is_active() -> bool:
    """True while some object holds the guard, so automatic collection is off."""
    return _holders > 0
