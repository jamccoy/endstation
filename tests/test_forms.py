"""Collected field errors."""

import pytest

from endstation.forms import ErrorCollector, FieldError, FormErrors


def test_empty_is_falsy():
    assert not FormErrors()
    assert not ErrorCollector()


def test_every_check_runs_in_one_pass():
    """The reason this is a value and not an exception raised on first failure."""
    errors = ErrorCollector()
    errors.add("period", "must be positive")
    errors.add("trim", "must be below 0.28")
    errors.add("graze", "must be between 0 and 90")
    assert len(errors.result()) == 3


def test_fields_are_reported_in_order():
    errors = ErrorCollector()
    errors.add("b", "second")
    errors.add("a", "first")
    assert errors.result().fields() == ("b", "a")


def test_for_field_selects_one_control():
    errors = ErrorCollector()
    errors.add("period", "must be positive")
    errors.add("period", "must be below 10000")
    errors.add("trim", "too large")
    assert len(errors.result().for_field("period")) == 2
    assert errors.result().for_field("missing") == ()


def test_form_errors_is_both_a_value_and_an_exception():
    """Downstream disagrees on which it wants; being both avoids a rewrite."""
    assert issubclass(FormErrors, Exception)
    errors = ErrorCollector()
    errors.add("period", "must be positive")
    with pytest.raises(FormErrors) as excinfo:
        errors.raise_if_any()
    assert excinfo.value.fields() == ("period",)


def test_raise_if_any_is_silent_when_clean():
    ErrorCollector().raise_if_any()


def test_str_lists_every_problem():
    errors = ErrorCollector()
    errors.add("period", "must be positive")
    errors.add("trim", "too large")
    text = str(errors.result())
    assert "period: must be positive" in text
    assert "trim: too large" in text


def test_field_error_is_hashable_and_immutable():
    error = FieldError("period", "must be positive")
    assert {error}
    with pytest.raises(AttributeError):
        error.field = "other"
