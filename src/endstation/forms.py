"""Field-level validation results, collected instead of raised.

This module is the pure half of a GUI. Widget code is the least testable part
of any project, and the value of a scientific application lies in defensible
numbers, so parsing and validation are kept out of the widgets entirely. A bug
in the untested layer can then produce a wrong layout but never a wrong number.

Errors are collected instead of being raised on the first failure. A form with
three bad fields should report all three problems at once, so that the user
does not have to fix them one at a time and rediscover the next one on each
attempt. This decision is the reason the result is a data type and not only an
exception.

Three layers answer three different questions, and keeping them separate
allows a validation routine to be used outside a GUI:

* the file or document layer asks whether this is a usable configuration at all;
* this module, and the ``build()`` functions that use it, ask whether this field is usable;
* the widget asks whether this control will accept the value.

A value outside a spin box's range is therefore reported here and passed through
verbatim; the clamping belongs in the panel, where the control that enforces the
range lives. Clamping at this layer would make the routine useless to a
caller that has no widget, such as a script, a test, or a CLI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Iterator

__all__ = ["FieldError", "FormErrors", "ErrorCollector"]


@dataclass(frozen=True, slots=True)
class FieldError:
    """A problem with one named input.

    ``field`` is the caller's own name for the control and is not a display
    label. It allows a window to attach the message to the offending widget
    instead of placing every problem in one status line.
    """

    field: str
    message: str

    def __str__(self) -> str:
        return f"{self.field}: {self.message}"


@dataclass(frozen=True, slots=True)
class FormErrors(Exception):
    """Every problem found in one pass over a form.

    The class is deliberately both a value and an exception. Downstream
    projects differ on which they want (one returns ``(settings, errors)`` and
    another raises), and forcing them to converge would mean rewriting working
    call sites for no behavioural gain. Because the type is both, each project
    keeps its own contract while sharing the type that passes between them.

    An instance is falsy when empty, so ``if errors:`` reads correctly.
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

    The `add`-then-`result` shape allows a `build()` function to read as a
    straight run of independent checks instead of nested conditionals::

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
