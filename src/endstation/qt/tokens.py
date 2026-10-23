"""Telling a result you still want from one you cancelled.

The mechanism is a monotonic counter. The window increments it whenever what
it is waiting for changes (a new request, a Cancel click, or the window
closing), and every request carries the value it was issued under. A worker
echoes that value back untouched, and a result whose token is not the current
one is dropped.

The counter neither replaces real cancellation nor is made redundant by it.
:mod:`endstation.qt.jobs` stops the work by raising through the progress
callback, while this module recognises a result that was already in flight
when Cancel was clicked. The worker may have finished between the click and the
reading of the flag, so a stale result can still arrive however promptly
cancellation acts. The two mechanisms therefore cover two different situations.

The counter is deliberately not protected by a lock. It is only incremented on
the GUI thread and only read for equality, and an int assignment is atomic
under the GIL. A mutex here would imply a concurrency requirement that does not
exist.
"""

from __future__ import annotations

__all__ = ["StaleGuard"]


class StaleGuard:
    """Issues request tokens and reports whether one is still current.

    Typical use in a window::

        self._guard = StaleGuard()

        def solve(self):
            token = self._guard.issue()
            self._runner.start(work, token=token, on_done=self._solved)

        def _solved(self, result, token):
            if self._guard.is_stale(token):
                return          # cancelled, or superseded by a newer request
            self._draw(result)

        def cancel(self):
            self._guard.invalidate()
    """

    def __init__(self) -> None:
        self._current = 0

    @property
    def current(self) -> int:
        """The token a result must carry to be accepted."""
        return self._current

    def issue(self) -> int:
        """Start a new request and return its token.

        Incrementing on issue, and not on completion, allows a second request
        to supersede a first that is still running: the older result comes
        back carrying a token that is no longer current, and is dropped.
        """
        self._current += 1
        return self._current

    def invalidate(self) -> None:
        """Abandon whatever is in flight without starting anything new.

        This is used for Cancel and for ``closeEvent``, since a window that is
        closing must not try to draw into widgets Qt is about to delete.
        """
        self._current += 1

    def is_current(self, token: int) -> bool:
        return token == self._current

    def is_stale(self, token: int) -> bool:
        """True if this result should be dropped; call sites read best in this form."""
        return token != self._current
