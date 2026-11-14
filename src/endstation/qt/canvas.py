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

:func:`restyle_toolbar` keeps a navigation toolbar's icons readable when the
theme changes while the application runs; matplotlib only chooses their
colour when it builds the toolbar. A pane's own toolbar follows the theme by
itself.

Everything here runs on the main thread. Workers return plain data, and the
window draws from it. See rule 2 in :mod:`endstation.qt`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from . import theming, use_qt_backend

if TYPE_CHECKING:
    from ..theme import Theme

__all__ = ["FigurePane", "restyle_toolbar", "show_message"]

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


def restyle_toolbar(toolbar, theme: Theme | None = None) -> int:
    """Redraw a matplotlib ``NavigationToolbar2QT``'s icons for the current colours.

    matplotlib picks the icon colour once, when it builds the toolbar: black
    icons as drawn, or recoloured to the foreground when the background is
    dark. A theme switched while the application runs leaves them dark on dark
    or pale on light until the next launch. Call this from a
    :func:`endstation.qt.theming.subscribe` callback, as :class:`FigurePane`
    does, for a toolbar a project builds itself.

    Pass the ``theme`` the callback received. When ``ThemeManager.changed``
    fires, the new application palette has not reached the toolbar yet (Qt
    delivers it through the event loop afterwards), so the toolbar's own
    palette would still give the old colours. With a theme, the colours come
    from :func:`endstation.qt.theming.palette` for the toolbar's own
    background and foreground roles; without one, from the toolbar's palette.

    From matplotlib 3.11 the toolbar's icons are drawn when painted, from the
    toolbar's palette at that moment, so they follow a theme on their own once
    the palette arrives. This then changes nothing: replacing them with fixed
    pixmaps would only lose that.

    The icons are found through matplotlib's private ``_actions`` and
    ``toolitems``, so this is guarded: on a toolbar that does not have them in
    the expected shape it changes nothing and raises nothing. Returns the
    number of icons replaced, which is 0 in each of these cases.
    """
    if _icons_follow_palette():
        return 0
    actions = getattr(toolbar, "_actions", None)
    items = getattr(toolbar, "toolitems", None)
    if not isinstance(actions, dict) or items is None:
        return 0
    try:
        colours = theming.palette(theme) if theme is not None else toolbar.palette()
        background = colours.color(toolbar.backgroundRole())
        foreground = colours.color(toolbar.foregroundRole())
        ratio = toolbar.devicePixelRatioF() or 1  # rarely 0, as matplotlib notes
        replaced = 0
        for entry in items:
            try:
                _text, _tooltip, image, callback = entry
            except (TypeError, ValueError):
                continue
            action = actions.get(callback)
            if image is None or action is None:
                continue
            icon = _toolbar_icon(f"{image}.png", background, foreground, ratio)
            if icon is not None:
                action.setIcon(icon)
                replaced += 1
        return replaced
    except Exception:  # noqa: BLE001 - private matplotlib API; never break a theme switch
        return 0


def _icons_follow_palette() -> bool:
    """True when matplotlib draws toolbar icons at paint time (3.11 and later)."""
    from matplotlib.backends import backend_qt

    return hasattr(backend_qt, "_IconEngine")


def _toolbar_icon(name: str, background: QColor, foreground: QColor, ratio: float) -> QIcon | None:
    """matplotlib's ``NavigationToolbar2QT._icon``, with the colours passed in.

    The same file choice (the ``_large`` variant when there is one) and the
    same rule: on a dark background the black glyph is refilled with the
    foreground colour. None when the image cannot be found.
    """
    from matplotlib import cbook

    regular = cbook._get_data_path("images", name)
    large = regular.with_name(regular.name.replace(".png", "_large.png"))
    path = large if large.exists() else regular
    if not path.exists():
        return None
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return None
    pixmap.setDevicePixelRatio(ratio)
    if background.value() < 128:
        mask = pixmap.createMaskFromColor(QColor("black"), Qt.MaskMode.MaskOutColor)
        pixmap.fill(foreground)
        pixmap.setMask(mask)
    return QIcon(pixmap)


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
            # A bound method, so Qt drops the connection with the pane.
            theming.subscribe(self._restyle_toolbar)
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

    def _restyle_toolbar(self, theme: Theme) -> None:
        if self.toolbar is not None:
            restyle_toolbar(self.toolbar, theme)

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
