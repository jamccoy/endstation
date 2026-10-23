"""Has Qt already deleted the C++ object behind this Python wrapper?

``RuntimeError: Internal C++ object (PySide6.QtWidgets.QLabel) already
deleted`` is the error raised when a queued signal arrives after the widget it
targets has been destroyed, for example when a worker finishes just as a
window closes, or a debounce timer fires during teardown. The Python object is
still alive and ordinary, but the C++ half has been deleted.

Two defences exist, and they apply to different situations:

* Hold a reference. For an object the application created and needs to
  outlive a local scope (a ``QMenu`` built in a method, or a model handed to a
  view), the fix is ownership and not a check. Qt was correct to delete the
  object; the bug was losing the only reference to it.
* Check before touching. For a callback that may legitimately arrive after
  its target is gone, there is nothing to own, because the widget is expected
  to have been deleted. The callback should check first.

This module provides the second defence. It belongs in a slot that a worker or
a timer can deliver late. Used as a blanket wrapper, it would hide the first
kind of bug without fixing it.
"""

from __future__ import annotations

from typing import Any

__all__ = ["is_alive"]


def is_alive(obj: Any) -> bool:
    """True if ``obj``'s underlying C++ object still exists.

    ``None`` is not alive, so ``if is_alive(self._canvas):`` covers both a
    never-created and an already-deleted widget in one condition.

    The function falls back to ``True`` when shiboken is unavailable. Without
    the binding's own registry there is no way to know, and returning False
    would make every guarded slot silently do nothing.
    """
    if obj is None:
        return False
    try:
        import shiboken6
    except ImportError:  # pragma: no cover - shiboken ships with PySide6
        return True
    return bool(shiboken6.isValid(obj))
