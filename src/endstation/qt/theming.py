"""Apply an :mod:`endstation.theme` to the running application, and let the user choose.

One :class:`ThemeManager` per ``QApplication``, created by :func:`install`
with the application's themes. It turns the chosen theme into a ``QPalette``
(under Fusion, so the palette governs every widget) and into matplotlib
settings, remembers the choice in :func:`endstation.qt.settings.settings`, and
emits ``changed`` so that each figure and each rendered page can restyle
itself; a widget connects through :func:`subscribe`.

``"system"`` follows the operating system's light or dark setting, live: Qt
reports a change of colour scheme and the manager re-applies it.

:class:`ThemeMenu` is the View > Theme submenu; every window builds one, and
all of them stay checked in step through the manager.
"""

from __future__ import annotations

import weakref
from collections.abc import Callable, Mapping

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import (QAction, QActionGroup, QColor, QGuiApplication,
                           QIcon, QPalette, QPixmap)
from PySide6.QtWidgets import QApplication, QMenu

from .. import theme as _theme
from ..theme import SYSTEM, Theme, rc_params
from .liveness import is_alive
from .settings import settings

__all__ = [
    "ThemeManager",
    "ThemeMenu",
    "current",
    "install",
    "manager",
    "palette",
    "subscribe",
    "swatch",
]

_KEY = "appearance/theme"
_PROPERTY = "_endstation_theme_manager"


def palette(theme: Theme) -> QPalette:
    """A ``QPalette`` for ``theme``, with disabled text dimmed to its muted colour."""
    role = QPalette.ColorRole
    group = QPalette.ColorGroup
    result = QPalette()
    entries = {
        role.Window: theme.window,
        role.WindowText: theme.text,
        role.Base: theme.base,
        role.AlternateBase: theme.alt_base,
        role.ToolTipBase: theme.base,
        role.ToolTipText: theme.text,
        role.PlaceholderText: theme.muted,
        role.Text: theme.text,
        role.Button: theme.button,
        role.ButtonText: theme.text,
        role.BrightText: theme.bad,
        role.Highlight: theme.highlight,
        role.HighlightedText: theme.highlight_text,
        role.Link: theme.link,
        role.LinkVisited: theme.link,
        role.Mid: theme.muted,
    }
    for which, color in entries.items():
        result.setColor(which, QColor(color))
    for which in (role.WindowText, role.Text, role.ButtonText):
        result.setColor(group.Disabled, which, QColor(theme.muted))
    # Light and Dark shading for Fusion's bevels, derived rather than listed.
    base = QColor(theme.button)
    result.setColor(role.Light, base.lighter(130))
    result.setColor(role.Midlight, base.lighter(115))
    result.setColor(role.Dark, base.darker(160))
    result.setColor(role.Shadow, base.darker(250))
    return result


class ThemeManager(QObject):
    """Holds the chosen theme and applies it to one application.

    ``themes`` is the application's menu of themes by key, in order;
    ``light`` and ``dark`` are the keys ``"system"`` resolves to.
    """

    changed = Signal(object)  # the resolved Theme

    def __init__(
        self,
        app: QApplication,
        themes: Mapping[str, Theme],
        *,
        light: str = "light",
        dark: str = "dark",
    ) -> None:
        super().__init__(app)
        if light not in themes or dark not in themes:
            raise ValueError(f"themes must include {light!r} and {dark!r}; have {', '.join(themes)}")
        self._app = app
        self.themes = dict(themes)
        self._light, self._dark = light, dark
        stored = str(settings().value(_KEY, SYSTEM))
        self._choice = stored if stored == SYSTEM or stored in self.themes else SYSTEM
        QGuiApplication.styleHints().colorSchemeChanged.connect(self._on_scheme_changed)

    @property
    def choice(self) -> str:
        """The stored choice: ``"system"`` or a key of :attr:`themes`."""
        return self._choice

    @property
    def theme(self) -> Theme:
        """The theme in effect, with ``"system"`` resolved."""
        if self._choice != SYSTEM:
            return self.themes[self._choice]
        scheme = QGuiApplication.styleHints().colorScheme()
        return self.themes[self._dark if scheme == Qt.ColorScheme.Dark else self._light]

    @property
    def light(self) -> Theme:
        """The theme ``"system"`` resolves to in light mode."""
        return self.themes[self._light]

    def set_choice(self, choice: str) -> None:
        """Choose a theme by key, or ``"system"``, and apply it."""
        if choice != SYSTEM and choice not in self.themes:
            raise ValueError(
                f"unknown theme {choice!r}; choose {SYSTEM!r} or one of "
                f"{', '.join(self.themes)}"
            )
        self._choice = choice
        store = settings()
        store.setValue(_KEY, choice)
        store.sync()
        self.apply()

    def apply(self) -> None:
        """Push the current theme into Qt and matplotlib, then announce it."""
        import matplotlib

        theme = self.theme
        self._app.setPalette(palette(theme))
        matplotlib.rcParams.update(rc_params(theme))
        self.changed.emit(theme)

    def _on_scheme_changed(self, _scheme) -> None:
        if self._choice == SYSTEM:
            self.apply()


def install(
    app: QApplication,
    themes: Mapping[str, Theme] | None = None,
    *,
    light: str = "light",
    dark: str = "dark",
) -> ThemeManager:
    """The application's manager, created and applied on first call.

    ``themes`` defaults to :data:`endstation.theme.THEMES`. Later calls return
    the existing manager and ignore their arguments, so any entry point may
    call it. Sets the Fusion style too: under the native styles a palette is
    only a suggestion.
    """
    existing = manager(app)
    if existing is not None:
        return existing
    app.setStyle("Fusion")
    created = ThemeManager(app, _theme.THEMES if themes is None else themes, light=light, dark=dark)
    app.setProperty(_PROPERTY, created)
    # Before the first apply, so each early subscriber is styled by it.
    for callback in _take_early():
        created.changed.connect(callback)
    created.apply()
    return created


def manager(app: QApplication | None = None) -> ThemeManager | None:
    """The manager installed on ``app`` (the running one by default), if any."""
    app = app or QApplication.instance()
    if app is None:
        return None
    found = app.property(_PROPERTY)
    return found if isinstance(found, ThemeManager) else None


def current(default: Theme = _theme.LIGHT) -> Theme:
    """The theme in effect, or ``default`` when no manager is installed."""
    found = manager()
    return found.theme if found is not None else default


#: Callbacks subscribed before any manager existed, as weak references, until
#: :func:`install` connects them.
_early: list[Callable[[], Callable[[Theme], None] | None]] = []


def subscribe(callback: Callable[[Theme], None]) -> None:
    """Call ``callback(theme)`` whenever the theme changes.

    A widget may subscribe before :func:`install` has run. The callback is
    then held until the manager exists and connected before its first
    ``apply``, so it is styled at install and on every change after. It used
    to be dropped instead, silently: a widget built a moment too early never
    followed the theme, and nothing said so. Until then the widget keeps the
    colours it was built with, which is also what a widget embedded in an
    application with no manager at all does.

    An early bound method is held weakly, so subscribing does not keep a
    widget alive; one whose object has gone by the time of :func:`install`
    is skipped, never called.

    Pass a bound method of a ``QObject``, never a lambda: Qt drops a
    connection to a method when its object is destroyed, but keeps calling
    a lambda, into a widget that no longer exists.
    """
    found = manager()
    if found is not None:
        found.changed.connect(callback)
        return
    try:
        _early.append(weakref.WeakMethod(callback))
    except TypeError:
        # Not a bound method: nothing to hold weakly, so it is held as is.
        _early.append(lambda: callback)


def _take_early() -> list[Callable[[Theme], None]]:
    """The early callbacks whose owners are still alive, and forget them all."""
    alive = []
    for ref in _early:
        callback = ref()
        if callback is None:
            continue
        owner = getattr(callback, "__self__", None)
        if isinstance(owner, QObject) and not is_alive(owner):
            continue
        alive.append(callback)
    _early.clear()
    return alive


class ThemeMenu(QMenu):
    """The View > Theme submenu, one per window, all kept in step.

    Each menu follows the manager's ``changed`` signal rather than its own
    clicks, so choosing in one window re-checks the others. Built with no
    manager installed, it lists :data:`endstation.theme.THEMES` and does
    nothing when chosen.
    """

    def __init__(self, parent=None) -> None:
        super().__init__("&Theme", parent)
        self._group = QActionGroup(self)
        self._group.setExclusive(True)
        found = manager()
        themes = found.themes if found is not None else _theme.THEMES
        choices = [(SYSTEM, "System")] + [(k, t.label) for k, t in themes.items()]
        for key, label in choices:
            action = self.addAction(label)
            action.setCheckable(True)
            action.setData(key)
            action.triggered.connect(self._chosen)
            self._group.addAction(action)
            if key == SYSTEM:
                self.addSeparator()
        if found is not None:
            found.changed.connect(self._sync)
        self._sync()

    def actions_by_key(self) -> dict[str, QAction]:
        return {a.data(): a for a in self._group.actions()}

    def _chosen(self) -> None:
        action = self.sender()
        found = manager()
        if found is not None and isinstance(action, QAction):
            found.set_choice(action.data())

    def _sync(self, _theme=None) -> None:
        found = manager()
        choice = found.choice if found is not None else SYSTEM
        for key, action in self.actions_by_key().items():
            action.setChecked(key == choice)


def swatch(color: str, size: int = 12) -> QIcon:
    """A square of ``color``, for a list entry that names a plotted line."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(color))
    return QIcon(pixmap)
