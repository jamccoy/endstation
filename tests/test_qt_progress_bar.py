"""The delayed progress bar, on its own and following a JobRunner."""

import threading

import pytest

pytest.importorskip("PySide6", reason="the qt extra is not installed")

from endstation.qt.jobs import JobRunner  # noqa: E402
from endstation.qt.progress_bar import DEFAULT_DELAY_MS, DelayedProgressBar  # noqa: E402

#: Comfortably past the delay, for a test that waits to see whether it fired.
PAST_DELAY_MS = DEFAULT_DELAY_MS * 3


@pytest.fixture
def bar(qtbot):
    made = DelayedProgressBar()
    qtbot.addWidget(made)
    return made


@pytest.fixture
def runner(qtbot):
    made = JobRunner()
    yield made
    made.cancel()
    made.wait(5_000)


# -- on its own --------------------------------------------------------------

def test_it_starts_hidden_and_indeterminate(bar):
    assert bar.isHidden() and bar.maximum() == 0 and not bar.pending


def test_begin_waits_out_the_delay_before_showing(bar, qtbot):
    bar.begin()
    assert bar.isHidden() and bar.pending
    qtbot.waitUntil(bar.isVisible, timeout=PAST_DELAY_MS)
    assert bar.maximum() == 0, "indeterminate until the first report"


def test_work_that_ends_inside_the_delay_never_shows(bar, qtbot):
    """The point of the delay: a quick job must not flash a bar."""
    bar.begin()
    bar.end()
    qtbot.wait(PAST_DELAY_MS)
    assert bar.isHidden() and not bar.pending


def test_a_report_makes_it_determinate(bar):
    bar.report(3, 10)
    assert (bar.minimum(), bar.maximum(), bar.value()) == (0, 10, 3)


def test_begin_resets_a_previous_run(bar):
    """A full bar left from the last run would claim work nobody has done."""
    bar.report(10, 10)
    bar.begin()
    assert bar.maximum() == 0


def test_the_delay_dies_with_the_bar(qtbot):
    """A timer outliving its bar once fired into a deleted QProgressBar."""
    from PySide6.QtCore import QCoreApplication, QEvent

    made = DelayedProgressBar()
    made.begin()
    made.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qtbot.wait(PAST_DELAY_MS)  # pytest-qt fails the test if a slot raises


def test_the_delay_can_be_chosen(qtbot):
    made = DelayedProgressBar(delay_ms=40)
    qtbot.addWidget(made)
    assert made.delay_ms == 40


# -- following a runner ---------------------------------------------------------

def _gated():
    gate = threading.Event()

    def work(progress=None):
        progress(1, 4)
        assert gate.wait(5), "the test never released the job"
        progress(2, 4)
        return "done"

    return gate, work


def test_a_fast_job_never_shows_the_bar(bar, runner, qtbot):
    bar.follow(runner)
    done = []
    runner.start(lambda progress=None: 1, on_done=done.append)
    qtbot.waitUntil(lambda: bool(done), timeout=5_000)
    qtbot.wait(PAST_DELAY_MS)
    assert bar.isHidden()


def test_a_slow_job_shows_it_reports_and_hides_when_done(bar, runner, qtbot):
    bar.follow(runner)
    gate, work = _gated()
    done = []
    runner.start(work, on_done=done.append)
    qtbot.waitUntil(bar.isVisible, timeout=PAST_DELAY_MS)
    qtbot.waitUntil(lambda: bar.maximum() == 4, timeout=5_000)
    assert bar.value() == 1
    gate.set()
    qtbot.waitUntil(lambda: bool(done), timeout=5_000)
    assert bar.isHidden() and not bar.pending


def test_cancel_hides_it_at_the_click_not_when_the_job_unwinds(bar, runner, qtbot):
    bar.follow(runner)
    gate, work = _gated()
    runner.start(work)
    qtbot.waitUntil(bar.isVisible, timeout=PAST_DELAY_MS)
    runner.cancel()
    assert bar.isHidden(), "the bar waited for the job instead of the click"
    gate.set()
    runner.wait(5_000)


def test_a_cancelled_job_does_not_move_its_successors_bar(bar, runner, qtbot):
    """A report queued just before Cancel can be delivered after the next job
    has begun. The cancelled job never reports again by itself, since its
    next report raises, so the late delivery is emitted here directly."""
    bar.follow(runner)
    gate, work = _gated()
    old = runner.start(work)
    qtbot.waitUntil(lambda: bar.maximum() == 4, timeout=5_000)
    runner.cancel()
    hold = threading.Event()
    runner.start(lambda progress=None: hold.wait(5))
    assert bar.maximum() == 0, "the new job's bar starts indeterminate"
    old.signals.progress.emit(3, 4)  # the late, queued report
    assert bar.maximum() == 0, "the cancelled job moved the new job's bar"
    gate.set()
    hold.set()
    runner.wait(5_000)


# -- the runner's signal ---------------------------------------------------------

def test_cancel_requested_is_emitted_once_per_cancel_of_a_running_job(runner, qtbot):
    seen = []
    runner.cancel_requested.connect(lambda: seen.append(True))
    runner.cancel()                 # nothing running
    gate, work = _gated()
    runner.start(work)
    runner.cancel()
    runner.cancel()                 # already asked
    assert seen == [True]
    gate.set()
    runner.wait(5_000)
