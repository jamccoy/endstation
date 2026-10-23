"""A matplotlib figure in a Qt window, with the parts every project rewrites.

The module provides three components, each of which existed in four or more
copies across the projects it was drawn from.

The placeholder is an empty axes with centred grey text, for the state before
anything has been computed. It is six lines, which were written out four times
in one repository alone, and its inconsistent use was the reason a fresh window
looked broken in one tab and explained itself in another.

The refusal applies the same idea in a different colour, for work that was
correctly declined, such as settings that cannot tile or a geometry with no
propagating orders. Rendering a refusal as an error dialog would misclassify
it: the software behaved correctly, and the user needs to read the reason
instead of dismissing a box. Keeping it on the canvas places the explanation
where the result would have been.

The visibility gate addresses the fact that a figure in a hidden tab still
repaints on every redraw request. This is cheap for one line plot but not for a
coverage raster or a 3-D layout, and the work is wasted because nobody is
looking. :meth:`FigurePane.draw` defers to the next ``showEvent`` instead.

Everything here runs on the main thread. Workers return plain data, and the
window draws from it. See rule 2 in :mod:`endstation.qt`.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from . import use_qt_backend

__all__ = ["FigurePane", "show_message"]

#: Grey, because a placeholder is information rather than a problem.
PLACEHOLDER_COLOR = "gray"
#: Firebrick, because a refusal is a decision the user needs to read.
REFUSAL_COLOR = "firebrick"


def show_message(
    figure,
    message: str,
    *,
    color: str = PLACEHOLDER_COLOR,
    weight: str = "normal",
    fontsize: int = 12,
) -> None:
    """Replace a figure's contents with one centred line of text.

    It works on any ``matplotlib.figure.Figure``, so it can be used from a
    plotting module that contains no Qt at all, as most of them do not.
    """
    figure.clear()
    axes = figure.add_subplot(111)
    axes.text(
        0.5, 0.5, message,
        ha="center", va="center",
        fontsize=fontsize, color=color, fontweight=weight,
        wrap=True, transform=axes.transAxes,
    )
    axes.set_axis_off()


class FigurePane(QWidget):
    """A figure, its canvas, and optionally a navigation toolbar.

    The pane uses composition instead of subclassing ``FigureCanvasQTAgg``.
    Both idioms were in use, sometimes in the same project. Composition was
    chosen because a pane that holds a canvas can also hold a toolbar, a
    placeholder and a visibility gate without any of them becoming part of the
    canvas's own interface.

    Draw into :attr:`figure` and call :meth:`draw`::

        pane = FigurePane(placeholder="Load a scan to see the profile")
        ax = pane.clear_axes()
        ax.plot(x, y)
        pane.draw()
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        figsize: tuple[float, float] = (8.0, 5.0),
        toolbar: bool = True,
        placeholder: str | None = None,
        tight_layout: bool = True,
    ) -> None:
        super().__init__(parent)

        # Before importing pyplot-adjacent machinery, so a Qt backend is bound
        # rather than the platform default -- on macOS that default is a second
        # native toolkit with its own event loop, inside a process already
        # running Qt's.
        use_qt_backend()

        from matplotlib.backends.backend_qtagg import (
            FigureCanvasQTAgg,
            NavigationToolbar2QT,
        )
        from matplotlib.figure import Figure

        self.figure = Figure(figsize=figsize, tight_layout=tight_layout)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.toolbar = NavigationToolbar2QT(self.canvas, self) if toolbar else None
        if self.toolbar is not None:
            layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

        self._pending_draw = False

        if placeholder is not None:
            self.show_placeholder(placeholder)

    # -- drawing ---------------------------------------------------------

    def clear_axes(self, *args, **kwargs):
        """Clear the figure and return one fresh axes, the usual first step."""
        self.figure.clear()
        return self.figure.add_subplot(*(args or (111,)), **kwargs)

    def draw(self) -> None:
        """Repaint now, or at the next ``showEvent`` if this pane is hidden.

        The deferral is the purpose of this method. A hidden tab's figure would
        otherwise be redrawn although nobody can see it, and on a raster or a
        3-D scene that causes a visible stall in the tab the user is looking at.
        """
        if self.isVisible():
            self._pending_draw = False
            self.canvas.draw_idle()
        else:
            self._pending_draw = True

    def showEvent(self, event) -> None:  # noqa: N802 - Qt's spelling
        super().showEvent(event)
        if self._pending_draw:
            self._pending_draw = False
            self.canvas.draw_idle()

    @property
    def draw_pending(self) -> bool:
        """True if a draw is waiting for this pane to become visible."""
        return self._pending_draw

    # -- states ----------------------------------------------------------

    def show_placeholder(self, message: str) -> None:
        """Show that nothing has been computed yet, in grey."""
        show_message(self.figure, message, color=PLACEHOLDER_COLOR)
        self.draw()

    def show_refusal(self, message: str) -> None:
        """Show that work was correctly declined, in firebrick on the canvas."""
        show_message(self.figure, message, color=REFUSAL_COLOR, weight="bold")
        self.draw()

    def plot(self, draw_fn: Callable[..., None], *args, **kwargs) -> None:
        """Clear, call ``draw_fn(figure, *args, **kwargs)``, then repaint.

        This allows a toolkit-free plotting module to own the drawing. That module takes
        a figure and knows nothing about Qt, so it stays testable under Agg.
        """
        self.figure.clear()
        draw_fn(self.figure, *args, **kwargs)
        self.draw()
