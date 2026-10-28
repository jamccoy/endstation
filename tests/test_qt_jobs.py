"""The pooled worker: results, failures, and cancellation that stops the work."""

import pytest

from endstation.progress import Cancelled

pytest.importorskip("PySide6", reason="the qt extra is not installed")

from endstation.qt.jobs import JobRunner  # noqa: E402


@pytest.fixture
def runner(qtbot):
    made = JobRunner()
    yield made
    made.cancel()
    made.wait(5_000)


def test_result_comes_back(runner, qtbot):
    seen = []
    job = runner.start(lambda progress=None: 42, on_done=seen.append)
    qtbot.waitUntil(lambda: bool(seen), timeout=5_000)
    assert seen == [42]
    assert job is runner.job


def test_a_callable_without_a_progress_keyword(runner, qtbot):
    seen = []
    runner.start(lambda: "plain", report_progress=False, on_done=seen.append)
    qtbot.waitUntil(lambda: bool(seen), timeout=5_000)
    assert seen == ["plain"]


def test_failure_becomes_a_signal_not_a_crash(runner, qtbot):
    """An exception escaping a slot under PySide6 can abort the process."""
    seen = []

    def boom(progress=None):
        raise ValueError("no good")

    runner.start(boom, on_fail=seen.append)
    qtbot.waitUntil(lambda: bool(seen), timeout=5_000)
    assert seen == ["ValueError: no good"]


def test_progress_is_reported(runner, qtbot):
    seen = []

    def work(progress=None):
        for i in range(5):
            progress(i, 5)
        return "done"

    runner.start(work, on_progress=lambda d, t: seen.append(d))
    qtbot.waitUntil(lambda: bool(len(seen) == 5), timeout=5_000)
    assert seen == [0, 1, 2, 3, 4]


def test_cancel_stops_the_work_rather_than_only_the_waiting(runner, qtbot):
    """The reason cancellation goes through the progress callback."""
    completed = []
    cancelled = []

    def work(progress=None):
        for i in range(1_000):
            progress(i, 1_000)
        completed.append(True)
        return "finished all 1000"

    job = runner.start(work, on_cancel=lambda: cancelled.append(True))
    job.cancel()
    qtbot.waitUntil(lambda: bool(cancelled), timeout=5_000)

    assert cancelled == [True]
    assert not completed, "the loop ran to completion; cancellation was cosmetic"


def test_cancelled_is_not_reported_as_a_failure(runner, qtbot):
    """The user asked for this. Rendering it as an error is a category mistake."""
    failures = []
    cancelled = []

    def work(progress=None):
        for i in range(1_000):
            progress(i, 1_000)

    job = runner.start(work, on_fail=failures.append,
                       on_cancel=lambda: cancelled.append(True))
    job.cancel()
    qtbot.waitUntil(lambda: bool(cancelled), timeout=5_000)
    assert failures == []


def test_a_callable_raising_cancelled_itself_is_honoured(runner, qtbot):
    cancelled = []

    def work(progress=None):
        raise Cancelled("core decided to stop")

    runner.start(work, on_cancel=lambda: cancelled.append(True))
    qtbot.waitUntil(lambda: bool(cancelled), timeout=5_000)
    assert cancelled == [True]


def test_overlapping_jobs_are_refused_not_queued(runner, qtbot):
    runner.start(lambda progress=None: 1)
    with pytest.raises(RuntimeError, match="already running"):
        runner.start(lambda progress=None: 2)
    runner.wait(5_000)


def test_busy_clears_before_the_callers_handler_runs(runner, qtbot):
    """Ordering bug: a handler asking for more work saw the runner still busy.

    Qt runs slots in connection order, so the runner's own bookkeeping has to be
    connected first. When it was connected last, a redraw requested on
    completion deferred forever and the result was never drawn.
    """
    observed = []
    runner.start(lambda progress=None: 1,
                 on_done=lambda _: observed.append(runner.busy()))
    qtbot.waitUntil(lambda: bool(observed), timeout=5_000)
    assert observed == [False]


def test_started_is_emitted_before_the_job_runs(runner, qtbot):
    """So a listener cannot miss a fast job by connecting too late."""
    seen = []
    runner.started.connect(lambda job: seen.append(job))
    job = runner.start(lambda progress=None: 1)
    assert seen == [job]


def test_cancel_after_completion_does_not_un_finish(runner, qtbot):
    """A request, not a guarantee -- callers must handle either outcome."""
    done = []
    job = runner.start(lambda progress=None: "quick", on_done=done.append)
    qtbot.waitUntil(lambda: bool(done), timeout=5_000)
    job.cancel()
    assert done == ["quick"]


# -- the worker thread's stack ------------------------------------------------

def test_the_worker_gets_a_main_thread_sized_stack(runner):
    """A pooled thread's default stack is 512 KiB on macOS, too small for LAPACK."""
    from endstation.qt.jobs import DEFAULT_STACK_BYTES

    assert DEFAULT_STACK_BYTES == 8 * 1024 * 1024
    assert runner.stack_size == DEFAULT_STACK_BYTES


def test_the_stack_size_can_be_overridden(qtbot):
    made = JobRunner(stack_size=16 * 1024 * 1024)
    assert made.stack_size == 16 * 1024 * 1024


@pytest.mark.parametrize("value", [None, 0])
def test_no_stack_size_leaves_the_platform_default(qtbot, value):
    assert JobRunner(stack_size=value).stack_size == 0


#: Run in a child interpreter because the failure this guards against is a
#: segfault, which would take the whole test session down with it rather than
#: fail one test.
_DENSE_SOLVE = """
import numpy as np
from PySide6.QtCore import QCoreApplication
from endstation.qt.jobs import JobRunner

app = QCoreApplication([])
runner = JobRunner()
seen = []

def solve(progress=None):
    rng = np.random.default_rng(0)
    n = 400
    a = rng.standard_normal((n, n)) + 1j * rng.standard_normal((n, n))
    b = rng.standard_normal(n) + 1j * rng.standard_normal(n)
    x = np.linalg.solve(a, b)
    return float(np.abs(a @ x - b).max())

runner.start(solve, on_done=seen.append, on_fail=seen.append)
assert runner.wait(60_000), "the solve did not finish"
app.processEvents()
print(seen[0])
"""


def test_a_dense_complex_solve_inside_a_job_does_not_crash():
    """The crash gratinglab met: np.linalg.solve segfaulting on a QThread.

    It reproduces on macOS, where a secondary thread's default stack is
    512 KiB. Windows gives a pooled thread enough stack even without the fix,
    so there this test only shows that a solve inside a job works; the test
    above it is what holds the stack size itself.
    """
    import subprocess
    import sys

    pytest.importorskip("numpy")
    probe = subprocess.run(
        [sys.executable, "-c", _DENSE_SOLVE],
        capture_output=True, encoding="utf-8", errors="replace", timeout=120,
    )
    assert probe.returncode == 0, (
        f"the child exited {probe.returncode}; a negative code or a Windows "
        f"access violation means the worker overran its stack\n{probe.stderr}"
    )
    assert float(probe.stdout.split()[-1]) < 1e-8
