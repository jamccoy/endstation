"""The progress protocol, the throttle, and cancellation through the callback."""

import pytest

from endstation.progress import Cancelled, cancelling, report, throttled


def test_report_with_no_callback_is_a_noop():
    assert report(None, 1, 2) is None


def test_report_forwards():
    seen = []
    report(lambda d, t: seen.append((d, t)), 3, 7)
    assert seen == [(3, 7)]


def test_report_lets_the_callback_raise():
    """Swallowing here would turn "stop" into "carry on"."""
    def refuses(done, total):
        raise Cancelled("stop")

    with pytest.raises(Cancelled):
        report(refuses, 1, 2)


def test_cancelled_is_an_ordinary_exception():
    """Not BaseException: it crosses code entitled to run its finally blocks."""
    assert issubclass(Cancelled, Exception)
    assert not issubclass(Cancelled, KeyboardInterrupt)


def test_throttle_collapses_updates_to_the_step_count():
    seen = []
    cb = throttled(lambda d, t: seen.append(d), steps=10)
    for i in range(201):
        cb(i, 200)
    # Buckets 0..10 inclusive, one emission each.
    assert len(seen) == 11


def test_throttle_of_none_is_none():
    assert throttled(None) is None


def test_throttle_handles_a_zero_total():
    seen = []
    cb = throttled(lambda d, t: seen.append(d), steps=10)
    cb(0, 0)
    assert seen == [0]


def test_cancellation_is_checked_on_every_call_not_every_emission():
    """The reason `cancelling` wraps `throttled` rather than including it.

    Throttling the cancellation check too would make a Cancel click land at the
    next percent instead of the next unit of work -- on a long sweep that is
    the difference between prompt and useless.
    """
    stop = False
    emitted = []
    cb = cancelling(throttled(lambda d, t: emitted.append(d), steps=10),
                    lambda: stop)

    with pytest.raises(Cancelled) as excinfo:
        for i in range(201):
            if i == 37:
                stop = True
            cb(i, 200)

    # Stopped at exactly 37, not at the next 10% boundary (40).
    assert "37 of 200" in str(excinfo.value)
    # And it emitted far fewer times than it was called.
    assert len(emitted) < 10


def test_cancelling_reports_before_it_raises():
    """The bar should show the last completed unit, not freeze one step short."""
    seen = []
    cb = cancelling(lambda d, t: seen.append(d), lambda: True)
    with pytest.raises(Cancelled):
        cb(5, 10)
    assert seen == [5]


def test_cancelling_without_a_callback_still_cancels():
    cb = cancelling(None, lambda: True)
    with pytest.raises(Cancelled):
        cb(1, 2)
