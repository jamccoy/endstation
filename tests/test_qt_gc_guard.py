"""The cycle collector stays on the GUI thread while the guard is held."""

import gc
import subprocess
import sys
import threading

import pytest

pytest.importorskip("PySide6", reason="the qt extra is not installed")

from PySide6.QtCore import QCoreApplication, QEvent, QObject  # noqa: E402

from endstation.qt import gc_guard  # noqa: E402
from endstation.qt.jobs import JobRunner  # noqa: E402


def _flush_deletions():
    """Let anything queued by deleteLater go before counting holders."""
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QCoreApplication.processEvents()


@pytest.fixture
def clean(qapp):
    _flush_deletions()
    assert not gc_guard.is_active(), "an earlier test left the guard held"
    assert gc.isenabled()
    yield
    _flush_deletions()


def test_holding_the_guard_turns_automatic_collection_off(clean, qtbot):
    holder = QObject()
    gc_guard.guard(holder)
    assert gc_guard.is_active()
    assert not gc.isenabled()
    holder.deleteLater()
    qtbot.waitUntil(lambda: not gc_guard.is_active(), timeout=5_000)
    assert gc.isenabled()


def test_holders_nest_and_the_last_one_restores_collection(clean, qtbot):
    first, second = QObject(), QObject()
    gc_guard.guard(first)
    gc_guard.guard(second)
    first.deleteLater()
    _flush_deletions()
    assert gc_guard.is_active()
    assert not gc.isenabled()
    second.deleteLater()
    qtbot.waitUntil(lambda: not gc_guard.is_active(), timeout=5_000)
    assert gc.isenabled()


def test_a_runner_holds_the_guard_only_when_asked(clean, qtbot):
    plain = JobRunner()
    assert not gc_guard.is_active()
    plain.deleteLater()

    guarded = JobRunner(gc_guard=True)
    assert gc_guard.is_active()
    assert not gc.isenabled()
    guarded.deleteLater()
    qtbot.waitUntil(lambda: not gc_guard.is_active(), timeout=5_000)
    assert gc.isenabled()


def test_jobs_never_collect_on_the_worker(clean, qtbot):
    """Every collection, including those a job's allocations make due, runs here."""
    gui_thread = threading.get_ident()
    seen = []

    def record(phase, info):
        if phase == "start":
            seen.append(threading.get_ident())

    def churn(progress=None):
        # Cycles, so only the cycle collector can free them, and enough of them
        # to pass generation 0's threshold many times over.
        for _ in range(20):
            junk = [[] for _ in range(5_000)]
            for a, b in zip(junk, junk[1:]):
                a.append(b)
                b.append(a)
            del junk
        return "done"

    runner = JobRunner(gc_guard=True)
    gc.callbacks.append(record)
    try:
        done = []
        for _ in range(3):
            runner.start(churn, on_done=done.append)
            qtbot.waitUntil(lambda: not runner.busy(), timeout=10_000)
        qtbot.wait(gc_guard.INTERVAL_MS * 3)
    finally:
        gc.callbacks.remove(record)
        runner.deleteLater()
    assert done == ["done"] * 3
    assert seen, "no collection ran at all, so the test proves nothing"
    assert set(seen) == {gui_thread}


def test_the_exit_hook_restores_collection_while_a_holder_is_alive(clean, qtbot):
    """A closed-but-undeleted window never releases the guard.

    The atexit hook must still hand collection back, and collect while Qt
    exists, or Python's final pass frees Qt garbage after Qt is gone and the
    process aborts with ``bool_dealloc``.
    """
    holder = QObject()
    gc_guard.guard(holder)
    try:
        gc_guard._restore_at_exit()
        assert gc.isenabled()
    finally:
        # Put back what a live holder expects, then release it normally.
        gc.disable()
        holder.deleteLater()
        qtbot.waitUntil(lambda: not gc_guard.is_active(), timeout=5_000)
    assert gc.isenabled()


def test_a_process_exits_cleanly_with_a_holder_still_alive(clean):
    probe = subprocess.run(
        [sys.executable, "-c", _HELD_AT_EXIT],
        capture_output=True, encoding="utf-8", errors="replace", timeout=60,
    )
    assert probe.returncode == 0, probe.stderr
    assert probe.stdout.split() == ["reached", "the", "end"]


#: A holder that is never deleted, as a closed-but-undeleted window is.
_HELD_AT_EXIT = """
import gc
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication
from endstation.qt import gc_guard

app = QApplication([])
holder = QObject()
gc_guard.guard(holder)
assert not gc.isenabled()
print("reached", "the", "end")
"""
