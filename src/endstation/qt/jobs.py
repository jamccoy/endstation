"""Running slow work off the GUI thread.

The contract is deliberately narrow:

* the callable runs on a worker thread and must return data, never a
  matplotlib artist (see rule 2 in :mod:`endstation.qt`);
* it may accept a ``progress`` keyword, which it forwards to the core;
* cancelling raises :class:`~endstation.progress.Cancelled` inside the
  callable, so it stops at the next reported step instead of running to
  completion and discarding the result.

The module is built on ``QThreadPool``/``QRunnable`` instead of a hand-managed
``QThread``. The QThread version aborted the interpreter when jobs ran back
to back, because the thread and its worker were being collected while the
thread was still finishing. That is a crash and not an exception, so a
front-end cannot defend against it. Letting Qt own the thread lifetime removes
that class of bug entirely.

Both cancellation mechanisms are used here, and they are not redundant. Raising
through the progress callback stops the work. The monotonic token
(:mod:`endstation.qt.tokens`) recognises a result that was already in flight
when Cancel was clicked and must not be rendered. Real cancellation does not
remove the race the token covers, since a worker may finish between the click
and the reading of the flag, so a front-end needs both mechanisms for the two
different situations.
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from ..progress import Cancelled

__all__ = ["Job", "JobRunner", "JobSignals"]


class JobSignals(QObject):
    """Signals for a :class:`Job`.

    This is a separate class because ``QRunnable`` is not a ``QObject`` and
    cannot carry signals itself.
    """

    progress = Signal(int, int)      # done, total
    finished = Signal(object)        # the callable's return value
    failed = Signal(str)             # unexpected exception, as text
    cancelled = Signal()


class Job(QRunnable):
    """Runs one callable on a pooled thread and reports what happened.

    Exactly one of ``finished`` / ``failed`` / ``cancelled`` is emitted.

    If ``report_progress`` is true the callable is passed a ``progress=``
    keyword. It is true by default because the keyword is what makes
    cancellation prompt; set it false for a callable that does not accept it.
    """

    def __init__(
        self,
        fn: Callable[..., Any],
        *args: Any,
        report_progress: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        self.signals = JobSignals()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self._report_progress = report_progress
        self._stop = False

    # Convenience passthroughs so callers need not reach into `.signals`.
    @property
    def progress(self) -> Signal:
        return self.signals.progress

    @property
    def finished(self) -> Signal:
        return self.signals.finished

    @property
    def failed(self) -> Signal:
        return self.signals.failed

    @property
    def cancelled(self) -> Signal:
        return self.signals.cancelled

    def cancel(self) -> None:
        """Ask the work to stop.

        This is safe to call from the GUI thread while the job runs, because
        it only sets a flag, which the progress callback reads on the worker
        thread. A bool assignment needs no lock.

        The call is a request and does not guarantee cancellation. The flag is
        read at the next progress report, so a job that finishes first emits
        ``finished`` and not ``cancelled``, since cancelling cannot undo
        completed work. The effect is not noticeable on the multi-second
        operations this class is meant for, but callers must handle either
        outcome and cannot assume that ``cancelled`` follows every
        :meth:`cancel`.
        """
        self._stop = True

    @property
    def cancelling(self) -> bool:
        return self._stop

    def run(self) -> None:
        """Entry point on the pooled worker thread."""

        def on_progress(done: int, total: int) -> None:
            if self._stop:
                # Raising *through* the core's progress hook is what makes
                # cancellation prompt: the loop abandons its remaining work
                # instead of finishing it and discarding the result.
                raise Cancelled(f"cancelled at {done} of {total}")
            self.signals.progress.emit(done, total)

        kwargs = dict(self._kwargs)
        if self._report_progress:
            kwargs["progress"] = on_progress

        try:
            result = self._fn(*self._args, **kwargs)
        except Cancelled:
            self.signals.cancelled.emit()
        except Exception as exc:  # noqa: BLE001 - broad on purpose, see below
            # A Python exception escaping a slot under PySide6 does not surface
            # as a friendly dialog: depending on version and excepthook state it
            # prints a traceback and aborts the process. Turning any failure
            # into a signal keeps the window alive and able to say what went
            # wrong. A worker that dies silently is worse than one that reports
            # badly -- the UI would wait forever for a signal that never comes.
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.signals.finished.emit(result)


class JobRunner(QObject):
    """Starts jobs and tracks whether one is in flight.

    Jobs run one at a time by design. The operations this class is meant for
    are heavy and usually write the same preview state, so overlapping them
    would race for both the CPU and the result; :meth:`busy` allows callers to
    refuse new work instead.
    """

    started = Signal(object)
    """A job began; carries the :class:`Job` itself.

    Exists so observers do not have to read :attr:`job` at the right moment.
    They did, and it was the wrong moment: a window wired its progress bar when
    a page announced it was busy, which pages emit *before* calling
    :meth:`start`, so ``job`` was still ``None`` and nothing got connected. The
    bar would appear and never clear.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(1)
        self._job: Job | None = None
        self._busy = False

    def busy(self) -> bool:
        return self._busy

    @property
    def job(self) -> Job | None:
        return self._job

    def start(
        self,
        fn: Callable[..., Any],
        *args: Any,
        on_done: Callable[[Any], None] | None = None,
        on_fail: Callable[[str], None] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
        report_progress: bool = True,
        **kwargs: Any,
    ) -> Job:
        """Run ``fn`` on a pooled thread, wiring the callbacks given."""
        if self._busy:
            raise RuntimeError("a job is already running")

        job = Job(fn, *args, report_progress=report_progress, **kwargs)

        # Bookkeeping first: Qt runs slots in connection order, so clearing
        # `busy` has to happen before the caller's handlers. It used to come
        # last, and a handler that asked for more work -- a redraw requested
        # once a computation lands, say -- saw the runner still busy and
        # deferred forever, so the result was never drawn at all.
        for signal in (job.signals.finished, job.signals.failed,
                       job.signals.cancelled):
            signal.connect(self._done)
        if on_progress is not None:
            job.signals.progress.connect(on_progress)
        if on_done is not None:
            job.signals.finished.connect(on_done)
        if on_fail is not None:
            job.signals.failed.connect(on_fail)
        if on_cancel is not None:
            job.signals.cancelled.connect(on_cancel)

        # Held on the runner so neither the job nor its signals object is
        # collected while the pooled thread is still using them.
        self._job = job
        self._busy = True
        # Announced before the job runs, so a listener cannot miss a fast job's
        # completion signals by connecting too late.
        self.started.emit(job)
        self._pool.start(job)
        return job

    def cancel(self) -> None:
        if self._job is not None:
            self._job.cancel()

    def wait(self, msec: int = 30_000) -> bool:
        """Block until the running job finishes. For teardown and tests."""
        return self._pool.waitForDone(msec)

    def _done(self, *_: Any) -> None:
        self._busy = False
