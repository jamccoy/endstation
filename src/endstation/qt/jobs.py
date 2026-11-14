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

Cancelling does two things, and a front-end needs both. Raising through the
progress callback stops the work. And a job that was asked to stop never
reaches the caller's ``on_done`` or ``on_fail``: a worker may finish between
the click and the next progress report, so a result can arrive after Cancel,
and the runner hands it to ``on_cancel`` instead. That second half is what a
token (:mod:`endstation.qt.tokens`) did by hand in every window; the runner
does it once, on the GUI thread, where the click and the delivery are ordered.

After a Cancel the next job can start at once. It queues behind the cancelled
one, which is still unwinding on the single worker thread, and runs when that
finishes. gratinglab's windows let a user solve again straight after a Cancel,
and refusing that until a long solve noticed its flag would read as a hang.
"""

from __future__ import annotations

from functools import partial
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from ..progress import Cancelled, throttled

__all__ = ["DEFAULT_STACK_BYTES", "Job", "JobRunner", "JobSignals", "describe_exception"]

#: Stack size for the runner's worker thread, matching the main thread's
#: default on macOS and Linux. A pooled thread otherwise gets the platform's
#: secondary-thread default, 512 KiB on macOS, and LAPACK's dense complex solve
#: overruns that: ``np.linalg.solve`` on a few-hundred-square matrix segfaulted
#: gratinglab's process on such a thread while running fine on the main thread
#: and on a plain ``threading.Thread``. A crash of that kind kills the whole
#: application rather than raising, so the larger stack is the default and not
#: an option to remember. The memory is reserved address space, committed only
#: as the stack actually grows.
DEFAULT_STACK_BYTES = 8 * 1024 * 1024


def describe_exception(exc: BaseException) -> str:
    """The default text for a failed job: ``"ValueError: message"``."""
    return f"{type(exc).__name__}: {exc}"


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

    Exactly one of ``finished`` / ``failed`` / ``cancelled`` is emitted. These
    are the raw outcome; :meth:`JobRunner.start` routes a cancelled job's late
    result to its ``on_cancel`` instead.

    If ``report_progress`` is true the callable is passed a ``progress=``
    keyword. It is true by default because the keyword is what makes
    cancellation prompt; set it false for a callable that does not accept it.

    Progress is emitted at most once per whole percent when ``throttle`` is
    true (see :func:`endstation.progress.throttled`): a 200-step scan would
    otherwise queue 200 cross-thread signals for a bar with about 100 visible
    states. The cancel check is not throttled; it runs on every report, so a
    Cancel takes effect at the next step, not the next percent.

    ``describe`` turns an unexpected exception into the ``failed`` text. An
    application can pass its own, to word a refusal differently from a bug.
    """

    def __init__(
        self,
        fn: Callable[..., Any],
        *args: Any,
        report_progress: bool = True,
        throttle: bool = True,
        describe: Callable[[BaseException], str] = describe_exception,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        self.signals = JobSignals()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self._report_progress = report_progress
        self._throttle = throttle
        self._describe = describe
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

        The call is a request: the flag is read at the next progress report,
        so a job that finishes first emits ``finished``. Through
        :meth:`JobRunner.start` that late result still goes to ``on_cancel``,
        never ``on_done``.
        """
        self._stop = True

    @property
    def cancelling(self) -> bool:
        return self._stop

    def run(self) -> None:
        """Entry point on the pooled worker thread."""
        emit = self.signals.progress.emit
        report = throttled(emit) if self._throttle else emit

        def on_progress(done: int, total: int) -> None:
            if self._stop:
                # Raising *through* the core's progress hook is what makes
                # cancellation prompt: the loop abandons its remaining work
                # instead of finishing it and discarding the result.
                raise Cancelled(f"cancelled at {done} of {total}")
            report(done, total)

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
            try:
                message = self._describe(exc)
            except Exception:  # noqa: BLE001 - a broken describe must not hang the UI
                message = describe_exception(exc)
            self.signals.failed.emit(message)
        else:
            self.signals.finished.emit(result)


class JobRunner(QObject):
    """Starts jobs, one at a time, and tracks whether one is in flight.

    Jobs run one at a time by design. The operations this class is meant for
    are heavy and usually write the same preview state, so overlapping them
    would race for both the CPU and the result. :meth:`start` refuses a new
    job while one runs, unless that one has been cancelled, in which case the
    new job queues behind it (see the module docstring).
    """

    started = Signal(object)
    """A job began; carries the :class:`Job` itself.

    Exists so observers do not have to read :attr:`job` at the right moment.
    They did, and it was the wrong moment: a window wired its progress bar when
    a page announced it was busy, which pages emit *before* calling
    :meth:`start`, so ``job`` was still ``None`` and nothing got connected. The
    bar would appear and never clear.
    """

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        stack_size: int | None = DEFAULT_STACK_BYTES,
        gc_guard: bool = False,
        describe: Callable[[BaseException], str] = describe_exception,
    ) -> None:
        """Create a runner with one worker thread.

        ``stack_size`` is the worker thread's stack in bytes, 8 MiB by default
        (see :data:`DEFAULT_STACK_BYTES`). ``None`` or ``0`` leaves the
        platform's default, which is too small on macOS for dense linear
        algebra.

        ``gc_guard`` runs Python's cycle collector on the GUI thread for as long
        as this runner exists, through :func:`endstation.qt.gc_guard.guard`.
        It is off by default because it disables automatic collection for the
        whole process. Turn it on in an application whose windows or figures
        can become garbage while a job runs, and construct the runner on the
        GUI thread when you do. See :mod:`endstation.qt.gc_guard`.

        ``describe`` words an unexpected exception for ``on_fail``; see
        :class:`Job`.
        """
        super().__init__(parent)
        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(1)
        if stack_size:
            # Before the first start(): a pool thread takes its stack size when
            # it is created, and this pool creates its one thread lazily.
            self._pool.setStackSize(stack_size)
        self._describe = describe
        self._job: Job | None = None
        self._busy = False
        if gc_guard:
            # Imported here so that a runner without the guard never registers
            # the guard's atexit hook.
            from .gc_guard import guard

            guard(self)

    def busy(self) -> bool:
        """Whether a job is running that has not been asked to stop."""
        return self._busy and self._job is not None and not self._job.cancelling

    @property
    def stack_size(self) -> int:
        """The worker thread's stack in bytes; 0 means the platform default."""
        return self._pool.stackSize()

    @property
    def job(self) -> Job | None:
        """The most recently started job."""
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
        throttle: bool = True,
        **kwargs: Any,
    ) -> Job:
        """Run ``fn`` on the worker thread, wiring the callbacks given.

        Exactly one of ``on_done``, ``on_fail`` and ``on_cancel`` is called. A
        job that was cancelled reaches only ``on_cancel``, whatever it
        returned or raised, and its progress stops reaching ``on_progress``.
        """
        if self.busy():
            raise RuntimeError("a job is already running")

        job = Job(fn, *args, report_progress=report_progress, throttle=throttle,
                  describe=self._describe, **kwargs)

        # Bookkeeping first: Qt runs slots in connection order, so clearing
        # `busy` has to happen before the caller's handlers. It used to come
        # last, and a handler that asked for more work -- a redraw requested
        # once a computation lands, say -- saw the runner still busy and
        # deferred forever, so the result was never drawn at all.
        for signal in (job.signals.finished, job.signals.failed,
                       job.signals.cancelled):
            signal.connect(partial(self._done, job))
        job.signals.progress.connect(partial(self._progress, job, on_progress))
        job.signals.finished.connect(partial(self._outcome, job, on_done, on_cancel))
        job.signals.failed.connect(partial(self._outcome, job, on_fail, on_cancel))
        job.signals.cancelled.connect(partial(self._cancelled, on_cancel))

        # Held on the runner so neither the job nor its signals object is
        # collected while the pooled thread is still using them. A cancelled
        # job that a new one replaced stays alive through the pool's queue and
        # the connections above until its outcome is delivered.
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
        """Block until every started job finishes. For teardown and tests."""
        return self._pool.waitForDone(msec)

    # -- delivery, on the GUI thread ---------------------------------------

    def _done(self, job: Job, *_: Any) -> None:
        # Only the newest job decides `busy`: a cancelled one finishing after
        # its replacement started must not mark the replacement idle.
        if job is self._job:
            self._busy = False

    @staticmethod
    def _progress(job: Job, callback, done: int, total: int) -> None:
        if callback is not None and not job.cancelling:
            callback(done, total)

    @staticmethod
    def _outcome(job: Job, callback, on_cancel, value: Any) -> None:
        if job.cancelling:
            if on_cancel is not None:
                on_cancel()
        elif callback is not None:
            callback(value)

    @staticmethod
    def _cancelled(on_cancel) -> None:
        if on_cancel is not None:
            on_cancel()
