"""Progress reporting and cancellation for slow operations.

This mechanism is deliberately placed here and not in a GUI layer. Decoding a
78 MB pattern file takes seconds, and so does a wavelength sweep. The main
shortcoming of a single-threaded callback is a front-end that can neither
report this progress nor stop the work. Keeping the mechanism toolkit-free means
it can be tested with plain functions and no GUI installed at all, which allows
the interface layer to stay thin enough to be trusted.

The protocol is one callback::

    def progress(done: int, total: int) -> None

called as work completes, with ``done`` rising to ``total``.

Cancellation needs no return-value protocol. A callback that wants to stop
the work raises (:class:`Cancelled`, by convention), and the loops let the
exception propagate. For this reason every :func:`report` call site should sit
directly in the loop and not inside a ``try``. Swallowing an exception from a
progress callback would silently turn "stop" into "carry on", which a cancel
button must never do.

The callback is what allows cancellation to stop the computation itself. A
Python thread cannot be killed and a NumPy-bound call has no check point, so a
caller that wants to interrupt the work has to be given a moment in which to do
so, and the progress callback provides that moment. Without it, cancelling can
only stop the waiting: the CPU keeps working, and the result is computed and
then discarded.
"""

from __future__ import annotations

from typing import Callable, Optional, Protocol

__all__ = ["Cancelled", "ProgressCallback", "cancelling", "report", "throttled"]


class ProgressCallback(Protocol):
    """The shape of a progress callback. Structural, so plain functions fit."""

    def __call__(self, done: int, total: int) -> None: ...  # pragma: no cover


class Cancelled(Exception):
    """Raised through a progress callback to abort a long operation.

    This exception does not indicate an error; it means the caller asked to
    stop. Front-ends should report it as a cancellation and not as a failure,
    and callers that catch broad exception groups need to let it through. A
    solver wrapping its callback in ``except Exception`` would swallow it and
    quietly restore the old behaviour, in which cancelling stopped only the
    waiting.

    It derives from :class:`Exception` and not from :class:`BaseException`
    on purpose. It passes through ordinary application code that is entitled to
    run ``finally`` blocks and close files on the way out. ``BaseException`` is
    intended for conditions that should skip that cleanup, and a cancellation
    is not one of them.
    """


def report(progress: Optional[ProgressCallback], done: int, total: int) -> None:
    """Call ``progress`` if there is one.

    Exceptions from the callback propagate on purpose, as the module docstring
    explains. This is a function so that every call site reads the same way and
    the ``None`` check lives in one place.
    """
    if progress is not None:
        progress(done, total)


def throttled(
    progress: Optional[ProgressCallback],
    *,
    steps: int = 100,
) -> Optional[ProgressCallback]:
    """Wrap ``progress`` so it fires at most ``steps`` times.

    Without this wrapper, a 200-wavelength scan emits 200 queued cross-thread
    signals to drive a bar with ~100 distinguishable states, and the updates the
    wrapper drops are ones that could not have been seen.

    Only the reporting is throttled. The wrapper calls the inner callback on
    every step where the bucket changes, but a caller that also checks for
    cancellation must do so on every call, unthrottled; otherwise a Cancel
    click takes effect at the next percent and not at the next unit of work.
    For this reason cancellation is not built into this function, since
    composing it here would make the throttle silently apply to both.

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

    ``should_stop`` is polled on every call, without throttling, so a cancel
    takes effect at the next unit of work. Pass an already-:func:`throttled`
    callback as ``progress`` when the reporting itself should be rate-limited::

        report = cancelling(throttled(on_progress), event.is_set)

    Reporting happens before the check so that the bar shows the last completed
    unit and does not freeze one step short of where the work stopped.
    """

    def report_and_check(done: int, total: int) -> None:
        report(progress, done, total)
        if should_stop():
            raise Cancelled(f"{message} at {done} of {total}")

    return report_and_check
