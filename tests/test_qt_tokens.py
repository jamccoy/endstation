"""Telling a result you still want from one you cancelled."""

from endstation.qt.tokens import StaleGuard


def test_a_fresh_token_is_current():
    guard = StaleGuard()
    assert guard.is_current(guard.issue())


def test_a_second_request_supersedes_the_first():
    """Bumping on issue is what makes a newer request win."""
    guard = StaleGuard()
    first = guard.issue()
    second = guard.issue()
    assert guard.is_stale(first)
    assert guard.is_current(second)


def test_invalidate_abandons_what_is_in_flight():
    guard = StaleGuard()
    token = guard.issue()
    guard.invalidate()
    assert guard.is_stale(token)


def test_invalidate_starts_nothing_new():
    """For Cancel and closeEvent: nothing should be accepted afterwards."""
    guard = StaleGuard()
    guard.issue()
    guard.invalidate()
    assert guard.is_stale(guard.current - 1)


def test_is_stale_is_the_negation_of_is_current():
    guard = StaleGuard()
    token = guard.issue()
    assert guard.is_stale(token) is not guard.is_current(token)


def test_tokens_are_monotonic():
    guard = StaleGuard()
    tokens = [guard.issue() for _ in range(5)]
    assert tokens == sorted(tokens)
    assert len(set(tokens)) == 5
