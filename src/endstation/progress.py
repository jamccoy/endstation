"""Progress reporting and cancellation for slow operations.

Deliberately here rather than in a GUI layer. Decoding a 78 MB pattern file
takes seconds, and so does a wavelength sweep; a front-end that cannot say so
-- or stop -- is the main thing wrong with a single-threaded callback. Keeping
the mechanism toolkit-free means it can be tested with plain functions and no
GUI installed at all, which is what lets the interface layer stay thin enough
to be worth trusting.

The protocol is one callback::

    def progress(done: int, total: int) -> None

called as work completes, with ``done`` rising to ``total``.

**Cancellation needs no return-value protocol.** A callback that wants to stop
the work simply raises -- :class:`Cancelled` by convention -- and the loops let
it propagate. That is why every :func:`report` call site should sit directly in
the loop rather than inside a ``try``: swallowing an exception from a progress
callback would silently turn "stop" into "carry on", which is the one behaviour
a cancel button must never have.

This is the piece that makes cancellation *real* rather than cosmetic. A Python
thread cannot be killed and a NumPy-bound call has no check point, so a caller
that wants to interrupt has to be handed a moment in which to do it; the
progress callback is that moment. Without it, cancelling can only stop the
*waiting* -- the CPU keeps working and the result is computed and thrown away.
"""

from __future__ import annotations

from typing import Callable, Optional, Protocol

__all__ = ["Cancelled", "ProgressCallback", "cancelling", "report", "throttled"]


class ProgressCallback(Protocol):
    """The shape of a progress callback. Structural, so plain functions fit."""

    def __call__(self, done: int, total: int) -> None: ...  # pragma: no cover


class Cancelled(Exception):
    """Raised through a progress callback to abort a long operation.

    Not an error: it means the caller asked to stop. Front-ends should report
    it as a cancellation rather than a failure, and callers that catch broad
    exception groups need to let this one through -- a solver wrapping its
    callback in ``except Exception`` would swallow it and quietly restore the
    old behaviour in which cancelling stopped only the waiting.

    Derives from :class:`Exception` rather than :class:`BaseException`
    deliberately. It crosses ordinary application code that is entitled to run
    ``finally`` blocks and close files on the way out; ``BaseException`` is for
    conditions that should skip that, and this is not one.
    """


def report(progress: Optional[ProgressCallback], done: int, total: int) -> None:
    """Call ``progress`` if there is one.

    Exceptions from the callback propagate on purpose -- see the module
    docstring. Kept as a function so every call site reads the same and the
    ``None`` check lives in one place.
    """
    if progress is not None:
        progress(done, total)


def throttled(
    progress: Optional[ProgressCallback],
    *,
    steps: int = 100,
) -> Optional[ProgressCallback]:
    """Wrap ``progress`` so it fires at most ``steps`` times.

    A 200-wavelength scan otherwise emits 200 queued cross-thread signals to
    drive a bar with ~100 distinguishable states, and the updates it drops are
    the ones nobody could have seen.

    **Only the reporting is throttled.** The wrapper calls the inner callback on
    every step where the bucket changes, but a caller that also checks for
    cancellation must do so on *every* call, unthrottled -- otherwise a Cancel
    click lands at the next percent rather than the next unit of work. That is
    why cancellation is not built into this function: composing it here would
    make the throttle silently apply to both.

    Returns ``None`` unchanged when given ``None``, so it is safe to wrap an
    absent callback.
    """
    if progress is None:
        return None

    last = -1

    def report_throttled(done: int, total: int) -> None:
        nonlocal last
        bucket = done * steps // total if total else steps
        # `!=` rather than `>`: a caller that restarts a sweep, or reports a
        # shrinking total, should still get updates rather than a frozen bar.
        if bucket != last:
            last = bucket
            progress(done, total)

    return report_throttled


def cancelling(
    progress: Optional[ProgressCallback],
    should_stop: Callable[[], bool],
    *,
    message: str = "cancelled",
) -> ProgressCallback:
    """Build a callback that reports, then raises :class:`Cancelled` if asked to.

    ``should_stop`` is polled on **every** call, not on throttled ones, so a
    cancel lands at the next unit of work. Pass an already-:func:`throttled`
    callback as ``progress`` when the reporting itself should be rate-limited::

        report = cancelling(throttled(on_progress), event.is_set)

    Reporting happens before the check so the bar shows the last completed unit
    rather than freezing one step short of where the work actually stopped.
    """

    def report_and_check(done: int, total: int) -> None:
        report(progress, done, total)
        if should_stop():
            raise Cancelled(f"{message} at {done} of {total}")

    return report_and_check
