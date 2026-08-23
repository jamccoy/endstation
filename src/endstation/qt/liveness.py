"""Has Qt already deleted the C++ object behind this Python wrapper?

``RuntimeError: Internal C++ object (PySide6.QtWidgets.QLabel) already
deleted`` is what a queued signal looks like when it arrives after the widget
it targets has been destroyed -- a worker finishing just as a window closes,
or a debounce timer firing during teardown. The Python object is still alive
and perfectly ordinary; the C++ half is gone.

Two defences exist, and they are for different situations:

* **Hold a reference.** For an object the application created and needs to
  outlive a local scope -- a ``QMenu`` built in a method, a model handed to a
  view -- the fix is ownership, not a check. Qt deleting it was correct; losing
  the only reference was the bug.
* **Check before touching.** For a callback that may legitimately arrive after
  its target is gone, there is nothing to own: the widget *should* be dead. Ask
  first.

This is the second one. Reach for it in a slot that a worker or a timer can
deliver late -- not as a blanket wrapper, which would hide the first kind of
bug rather than fix it.
"""

from __future__ import annotations

from typing import Any

__all__ = ["is_alive"]


def is_alive(obj: Any) -> bool:
    """True if ``obj``'s underlying C++ object still exists.

    ``None`` is not alive, so ``if is_alive(self._canvas):`` covers both a
    never-created and an already-deleted widget in one condition.

    Falls back to ``True`` when shiboken is unavailable. That is the honest
    answer rather than a safe-looking one: without the binding's own registry
    there is no way to know, and returning False would make every guarded slot
    silently do nothing.
    """
    if obj is None:
        return False
    try:
        import shiboken6
    except ImportError:  # pragma: no cover - shiboken ships with PySide6
        return True
    return bool(shiboken6.isValid(obj))
