"""Field-level validation results, collected rather than raised.

The pure half of a GUI. Widget code is the least testable part of any project,
and the value of a scientific application is defensible numbers, so parsing and
validation are kept out of the widgets entirely: a bug in the untested layer
then produces a wrong *layout*, never a wrong *number*.

**Errors are collected, not raised on the first failure.** A form with three bad
fields should report three problems, not make the user fix them one at a time
and rediscover the next one on each attempt. That single decision is why this is
a data type rather than an exception.

Three layers answer three different questions, and keeping them apart is what
makes a validation routine usable outside a GUI:

* the file/document layer -- is this a usable *configuration* at all?
* here, and the ``build()`` functions that use it -- is this *field* usable?
* the widget -- will this *control* accept it?

A value outside a spin box's range is therefore reported here and passed through
verbatim; the clamping belongs in the panel, where the control that enforces the
range actually lives. Clamping at this layer would make the routine useless to a
caller that has no widget -- a script, a test, or a CLI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Iterator

__all__ = ["FieldError", "FormErrors", "ErrorCollector"]


@dataclass(frozen=True, slots=True)
class FieldError:
    """A problem with one named input.

    ``field`` is the caller's own name for the control, not a display label:
    it is what lets a window attach the message to the offending widget rather
    than dumping every problem into one status line.
    """

    field: str
    message: str

    def __str__(self) -> str:
        return f"{self.field}: {self.message}"


@dataclass(frozen=True, slots=True)
class FormErrors(Exception):
    """Every problem found in one pass over a form.

    Both a value and an exception, deliberately. Downstream projects disagree
    on which they want -- one returns ``(settings, errors)``, another raises --
    and forcing them to converge would mean rewriting working call sites for no
    behavioural gain. Being both lets each keep its own contract while sharing
    the type that crosses between them.

    Falsy when empty, so ``if errors:`` reads correctly.
    """

    errors: tuple[FieldError, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.errors)

    def __len__(self) -> int:
        return len(self.errors)

    def __iter__(self) -> Iterator[FieldError]:
        return iter(self.errors)

    def __str__(self) -> str:
        if not self.errors:
            return "no errors"
        return "\n".join(str(e) for e in self.errors)

    def fields(self) -> tuple[str, ...]:
        """The names that failed, in order, for a widget layer to highlight."""
        return tuple(e.field for e in self.errors)

    def for_field(self, name: str) -> tuple[FieldError, ...]:
        """Every problem reported against one control."""
        return tuple(e for e in self.errors if e.field == name)


@dataclass
class ErrorCollector:
    """Accumulates :class:`FieldError`s during one validation pass.

    The `add`-then-`result` shape exists so a `build()` function reads as a
    straight run of independent checks rather than as nested conditionals::

        errors = ErrorCollector()
        if period <= 0:
            errors.add("period", "must be positive")
        if not 0 <= trim < MAX_TRIM:
            errors.add("trim", f"must be between 0 and {MAX_TRIM}")
        errors.raise_if_any()

    Every check runs, so every problem is found in one pass.
    """

    errors: list[FieldError] = field(default_factory=list)

    def add(self, name: str, message: str) -> None:
        self.errors.append(FieldError(name, message))

    def extend(self, items: Iterable[FieldError]) -> None:
        self.errors.extend(items)

    def __bool__(self) -> bool:
        return bool(self.errors)

    def __len__(self) -> int:
        return len(self.errors)

    def result(self) -> FormErrors:
        """The collected problems as an immutable value."""
        return FormErrors(tuple(self.errors))

    def raise_if_any(self) -> None:
        """Raise :class:`FormErrors` if anything was collected."""
        if self.errors:
            raise self.result()
