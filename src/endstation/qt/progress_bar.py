"""A progress bar that appears only when the work is slow enough to need one.

A job that finishes in under a frame or two should not flash a bar on and off:
that reads as a glitch rather than as feedback. :class:`DelayedProgressBar`
stays hidden for :data:`DEFAULT_DELAY_MS` after :meth:`~DelayedProgressBar.begin`
and appears only if the work is still going. It is indeterminate (a moving
stripe) until the first :meth:`~DelayedProgressBar.report`, determinate after,
and :meth:`~DelayedProgressBar.end` hides it.

:meth:`~DelayedProgressBar.follow` wires all of that to a
:class:`~endstation.qt.jobs.JobRunner`: every job the runner starts begins the
bar, its progress drives it, and its outcome or a Cancel ends it. An
application with one bar for one runner needs nothing else. One that routes a
job to one of several bars (gratinglab's solver tabs, each with its own) calls
the three methods itself.

The delay timer is a child of the bar, so it dies with the bar. A timer that
outlived its widget fired into a deleted progress bar once on macOS, inside the
next test's setup, and an exception escaping a slot under PySide6 can abort the
process.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer, Slot
from PySide6.QtWidgets import QProgressBar, QWidget

from .jobs import Job, JobRunner

__all__ = ["DEFAULT_DELAY_MS", "DelayedProgressBar"]

#: How long a job runs before its bar appears. 150 ms is about nine frames:
#: long enough that a quick job never shows one, short enough that a slow one
#: is acknowledged before a user wonders whether the click registered.
DEFAULT_DELAY_MS = 150


class DelayedProgressBar(QProgressBar):
    """A ``QProgressBar`` hidden until work has run for ``delay_ms``."""

    def __init__(self, parent: QWidget | None = None, *,
                 delay_ms: int = DEFAULT_DELAY_MS) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(delay_ms)
        self._timer.timeout.connect(self.show)
        self._job: Job | None = None
        self.setRange(0, 0)
        self.hide()

    @property
    def delay_ms(self) -> int:
        return self._timer.interval()

    @property
    def pending(self) -> bool:
        """Whether the bar is waiting out its delay, about to appear."""
        return self._timer.isActive()

    def begin(self) -> None:
        """Work has started: arm the delay, and start indeterminate.

        The range is reset because the previous run's is meaningless for work
        that has not reported yet, and keeping it would show a full bar for
        no work done.
        """
        self.setRange(0, 0)
        self.hide()
        self._timer.start()

    def report(self, done: int, total: int) -> None:
        """Progress: ``done`` of ``total``. The bar becomes determinate."""
        if self.maximum() != total:
            self.setRange(0, total)
        self.setValue(done)

    def end(self) -> None:
        """The work is over, however it ended: hide, and disarm the delay."""
        self._timer.stop()
        self.hide()

    def follow(self, runner: JobRunner) -> None:
        """Drive this bar from every job ``runner`` starts from now on."""
        runner.started.connect(self._follow_job)
        runner.cancel_requested.connect(self.end)

    @Slot(object)
    def _follow_job(self, job: Job) -> None:
        self.begin()
        job.signals.progress.connect(self._job_progress)
        for signal in (job.signals.finished, job.signals.failed,
                       job.signals.cancelled):
            signal.connect(self._job_over)
        self._job = job

    @Slot(int, int)
    def _job_progress(self, done: int, total: int) -> None:
        # A cancelled job's last reports, and those of a job a newer one has
        # replaced, must not move the bar the next job owns.
        job = self._job
        if job is not None and self.sender() is job.signals and not job.cancelling:
            self.report(done, total)

    @Slot()
    @Slot(object)
    @Slot(str)
    def _job_over(self, *_args) -> None:
        job = self._job
        if job is not None and self.sender() is job.signals:
            self.end()
