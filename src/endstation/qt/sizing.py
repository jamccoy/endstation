"""Layout floors that cannot promise less than their contents need.

A ``QScrollArea`` with ``setWidgetResizable(True)`` will not shrink its widget
below that widget's own ``minimumSizeHint``. Declaring a ``minimumWidth`` under
that figure creates a constraint Qt cannot satisfy, and Qt responds with a
horizontal scrollbar and a clipped control. This defect shipped twice without
being noticed, because nothing in the suite asserted on a pixel.

The width is derived and not hardcoded. The number depends on the platform's
push-button metrics and scrollbar width, so a literal that is right on one
machine is wrong on another, and CI runs three. Tests should assert on the
invariant instead of restating a constant.
"""

from __future__ import annotations

from PySide6.QtWidgets import QScrollArea

__all__ = ["fit_width_to_contents"]


def fit_width_to_contents(scroller: QScrollArea) -> int:
    """Set ``scroller``'s minimum width to what its widget needs.

    The width is the content minimum, plus the vertical scrollbar it may grow,
    plus both frame edges. The figure is returned so that a caller can log or
    assert on it.
    """
    widget = scroller.widget()
    if widget is None:  # pragma: no cover - a scroller with no content
        return scroller.minimumWidth()

    needed = (
        widget.minimumSizeHint().width()
        + scroller.verticalScrollBar().sizeHint().width()
        + 2 * scroller.frameWidth()
    )
    scroller.setMinimumWidth(needed)
    return needed
