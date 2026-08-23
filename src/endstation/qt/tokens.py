"""Telling a result you still want from one you cancelled.

A monotonic counter. The window bumps it whenever what it is waiting for
changes -- a new request, a Cancel click, the window closing -- and every
request carries the value it was issued under. A worker echoes that value back
untouched, and a result whose token is not the current one is dropped.

**Not a substitute for real cancellation, and not made redundant by it.**
:mod:`endstation.qt.jobs` stops the work by raising through the progress
callback; this recognises the result that was *already in flight* when Cancel
was clicked. The worker may have finished between the click and the flag being
read, so a stale result can still arrive no matter how prompt cancellation is.
Belt and braces, for two different situations.

Deliberately not a lock. It is only ever bumped on the GUI thread and only ever
read for equality, and an int assignment is atomic under the GIL; introducing a
mutex here would suggest a concurrency story that does not exist.
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

        Bumping on *issue* rather than on completion is what makes a second
        request supersede a first that is still running: the older result comes
        back carrying a token that is no longer current, and is dropped.
        """
        self._current += 1
        return self._current

    def invalidate(self) -> None:
        """Abandon whatever is in flight without starting anything new.

        For Cancel, and for ``closeEvent`` -- a window that is closing must not
        try to draw into widgets Qt is about to delete.
        """
        self._current += 1

    def is_current(self, token: int) -> bool:
        return token == self._current

    def is_stale(self, token: int) -> bool:
        """True if this result should be dropped. The form call sites read best in."""
        return token != self._current
