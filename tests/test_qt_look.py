"""Settings, themes, remembered folders and layout, and the Help menu."""

import pytest

pytest.importorskip("PySide6", reason="the qt extra is not installed")

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget  # noqa: E402

from endstation import theme  # noqa: E402
from endstation.qt import help_menu, recent, settings, theming  # noqa: E402


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Settings redirected to a fresh INI file, and no theme manager installed."""
    monkeypatch.setenv("ENDSTATION_TEST_SETTINGS", str(tmp_path / "s.ini"))
    settings.configure("endstation-tests", env="ENDSTATION_TEST_SETTINGS")
    app = QApplication.instance()
    previous = app.property(theming._PROPERTY)
    app.setProperty(theming._PROPERTY, None)
    theming._early.clear()
    yield tmp_path / "s.ini"
    theming._early.clear()
    app.setProperty(theming._PROPERTY, previous)
    settings.configure("endstation", env=None)


class TestSettings:
    def test_the_variable_redirects_the_store(self, store, qapp):
        settings.settings().setValue("x/y", 3)
        settings.settings().sync()
        assert store.exists()
        assert int(settings.settings().value("x/y")) == 3


class TestTheming:
    def test_install_applies_the_saved_choice(self, store, qapp):
        settings.settings().setValue("appearance/theme", "dark")
        managed = theming.install(qapp)
        assert managed.theme is theme.DARK
        assert qapp.palette().window().color().name() == theme.DARK.window
        assert theming.install(qapp) is managed, "a second install returns the first"

    def test_a_choice_is_saved_and_announced(self, store, qapp, qtbot):
        managed = theming.install(qapp)
        with qtbot.waitSignal(managed.changed) as blocker:
            managed.set_choice("solarized-dark")
        assert blocker.args == [theme.SOLARIZED_DARK]
        assert settings.settings().value("appearance/theme") == "solarized-dark"

    def test_an_unknown_choice_is_refused(self, store, qapp):
        with pytest.raises(ValueError, match="unknown theme"):
            theming.install(qapp).set_choice("plaid")

    def test_an_application_brings_its_own_themes(self, store, qapp):
        mine = {"light": theme.LIGHT, "dark": theme.HIGH_CONTRAST}
        managed = theming.install(qapp, mine)
        managed.set_choice("dark")
        assert managed.theme is theme.HIGH_CONTRAST
        menu = theming.ThemeMenu()
        assert list(menu.actions_by_key()) == ["system", "light", "dark"]

    def test_menus_stay_in_step(self, store, qapp):
        theming.install(qapp)
        first, second = theming.ThemeMenu(), theming.ThemeMenu()
        first.actions_by_key()["dark"].trigger()
        assert second.actions_by_key()["dark"].isChecked()

    def test_a_widget_subscribed_before_install_follows_the_theme(self, store, qapp, qtbot):
        """It used to be dropped: a widget built a moment before install()
        never followed the theme, and nothing said so."""
        class Pane(QWidget):
            def __init__(self):
                super().__init__()
                self.seen = []

            def restyle(self, chosen):
                self.seen.append(chosen.key)

        pane = Pane()
        qtbot.addWidget(pane)
        theming.subscribe(pane.restyle)
        settings.settings().setValue("appearance/theme", "dark")
        managed = theming.install(qapp)
        assert pane.seen == ["dark"], "install's first apply should style it"
        managed.set_choice("light")
        assert pane.seen == ["dark", "light"]

    def test_an_early_subscriber_is_not_kept_alive_by_subscribing(self, store):
        import gc
        import weakref

        class Owner:
            def restyle(self, chosen):
                pass

        owner = Owner()
        ref = weakref.ref(owner)
        theming.subscribe(owner.restyle)
        del owner
        gc.collect()
        assert ref() is None

    def test_a_widget_destroyed_before_install_is_never_called(self, store, qapp):
        from PySide6.QtCore import QCoreApplication, QEvent

        calls = []

        class Pane(QWidget):
            def restyle(self, chosen):
                calls.append(chosen)

        pane = Pane()
        theming.subscribe(pane.restyle)
        pane.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        theming.install(qapp)       # must neither call it nor raise
        assert calls == []

    def test_current_without_a_manager_is_the_default(self, store):
        assert theming.current() is theme.LIGHT
        assert theming.current(theme.DARK) is theme.DARK


def _icon_brightness(toolbar, callback="home") -> float:
    """Mean HSV value of an action icon's opaque pixels, 0 to 255."""
    import warnings

    with warnings.catch_warnings():
        # matplotlib 3.11's icon engine reads a Qt attribute PySide6 6.12
        # deprecates; not this suite's to fix, and it fails under -W error.
        warnings.simplefilter("ignore", DeprecationWarning)
        image = toolbar._actions[callback].icon().pixmap(24, 24).toImage()
    total = weight = 0.0
    for y in range(image.height()):
        for x in range(image.width()):
            colour = image.pixelColor(x, y)
            total += colour.value() * colour.alphaF()
            weight += colour.alphaF()
    assert weight > 0, "the icon has no opaque pixels to measure"
    return total / weight


@pytest.fixture
def fixed_icons(monkeypatch):
    """matplotlib before 3.11, which colours its icons once, whatever is installed."""
    from endstation.qt import canvas

    monkeypatch.setattr(canvas, "_icons_follow_palette", lambda: False)


class TestToolbarIcons:
    """A toolbar's icons stay readable when the theme changes while running.

    Before matplotlib 3.11 the icons are coloured once, when the toolbar is
    built, and :func:`restyle_toolbar` redraws them; from 3.11 they are drawn
    from the palette when painted. The `fixed_icons` tests take the first
    path on any matplotlib.
    """

    def test_a_pane_toolbar_follows_a_live_theme_switch(self, store, qapp, qtbot):
        from endstation.qt.canvas import FigurePane

        managed = theming.install(qapp)
        managed.set_choice("light")
        pane = FigurePane()
        qtbot.addWidget(pane)
        qapp.processEvents()
        on_light = _icon_brightness(pane.toolbar)

        managed.set_choice("dark")
        qapp.processEvents()
        on_dark = _icon_brightness(pane.toolbar)
        assert on_dark > on_light + 100, (on_light, on_dark)

        managed.set_choice("light")
        qapp.processEvents()
        assert _icon_brightness(pane.toolbar) == pytest.approx(on_light, abs=1)

    def test_fixed_icons_are_redrawn_from_the_theme_not_the_palette(
        self, store, qapp, qtbot, fixed_icons
    ):
        from endstation.qt.canvas import FigurePane

        managed = theming.install(qapp)
        managed.set_choice("light")
        pane = FigurePane()
        qtbot.addWidget(pane)
        on_light = _icon_brightness(pane.toolbar)
        # No event processing: the palette has not reached the toolbar when
        # `changed` fires, so the icons must come from the theme it carries.
        managed.set_choice("dark")
        assert _icon_brightness(pane.toolbar) > on_light + 100

    def test_a_toolbar_built_before_install_is_restyled_by_it(
        self, store, qapp, qtbot, fixed_icons
    ):
        from endstation.qt.canvas import FigurePane

        settings.settings().setValue("appearance/theme", "dark")
        qapp.setPalette(theming.palette(theme.LIGHT))
        pane = FigurePane()
        qtbot.addWidget(pane)
        on_light = _icon_brightness(pane.toolbar)
        theming.install(qapp)
        assert _icon_brightness(pane.toolbar) > on_light + 100

    def test_the_helper_restyles_a_toolbar_a_project_builds(self, store, qapp, qtbot, fixed_icons):
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
        from matplotlib.figure import Figure

        from endstation.qt.canvas import restyle_toolbar

        qapp.setPalette(theming.palette(theme.LIGHT))
        holder = QWidget()
        qtbot.addWidget(holder)
        toolbar = NavigationToolbar2QT(FigureCanvasQTAgg(Figure()), holder)
        on_light = _icon_brightness(toolbar)
        assert restyle_toolbar(toolbar, theme.DARK) == len(toolbar._actions)
        assert _icon_brightness(toolbar) > on_light + 100

    def test_icons_that_follow_the_palette_are_left_alone(self, qapp, qtbot, monkeypatch):
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
        from matplotlib.figure import Figure

        from endstation.qt import canvas

        monkeypatch.setattr(canvas, "_icons_follow_palette", lambda: True)
        holder = QWidget()
        qtbot.addWidget(holder)
        toolbar = NavigationToolbar2QT(FigureCanvasQTAgg(Figure()), holder)
        assert canvas.restyle_toolbar(toolbar, theme.DARK) == 0

    def test_the_helper_does_nothing_to_a_toolbar_it_does_not_recognise(self, qtbot, fixed_icons):
        from PySide6.QtWidgets import QToolBar

        from endstation.qt.canvas import restyle_toolbar

        plain = QToolBar()
        qtbot.addWidget(plain)
        assert restyle_toolbar(plain, theme.DARK) == 0
        plain._actions = {"home": object()}
        plain.toolitems = [("Home", "tip", "no-such-image", "home"), "malformed"]
        assert restyle_toolbar(plain, theme.DARK) == 0
        plain.toolitems = [("Home", "tip", "home", "home")]   # setIcon on a non-action
        assert restyle_toolbar(plain, theme.DARK) == 0

    def test_a_destroyed_pane_is_left_alone(self, store, qapp, fixed_icons):
        from PySide6.QtCore import QCoreApplication, QEvent

        from endstation.qt.canvas import FigurePane

        managed = theming.install(qapp)
        pane = FigurePane()
        pane.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        managed.set_choice("dark")      # must not reach the deleted toolbar


class TestRecent:
    def test_folders_are_per_kind_and_survive_only_while_they_exist(self, store, tmp_path):
        scans = tmp_path / "scans"
        scans.mkdir()
        recent.remember("scans", scans / "a.spm")
        assert recent.start_in("scans", "b.spm") == str(scans.resolve() / "b.spm")
        assert recent.start_in("exports") == ""
        scans.rmdir()
        assert recent.start_in("scans", fallback="home") == "home"

    def test_layout_round_trips(self, store, qtbot):
        window = QMainWindow()
        qtbot.addWidget(window)
        window.show()
        window.resize(640, 480)
        qtbot.waitUntil(lambda: window.height() == 480)
        recent.save_layout(window, "main")
        again = QMainWindow()
        qtbot.addWidget(again)
        assert recent.restore_layout(again, "main")
        again.show()
        qtbot.waitUntil(lambda: again.height() == 480)
        assert not recent.restore_layout(QMainWindow(), "other")


class TestHelpMenu:
    def test_about_then_grouped_pages(self, qtbot, monkeypatch):
        window = QMainWindow()
        qtbot.addWidget(window)
        opened, shown = [], []
        monkeypatch.setattr(help_menu.QMessageBox, "about",
                            lambda parent, title, text: shown.append((title, text)))
        menu = help_menu.install_help_menu(
            window,
            about_title="About thing",
            about_text=lambda: "thing 1.0",
            pages=[[("Guide", lambda: opened.append("guide"))], [],
                   [("Theory", lambda: opened.append("theory"))]],
        )
        labels = [a.text() for a in menu.actions()]
        assert labels == ["About thing", "", "Guide", "", "Theory"]
        assert window._endstation_help_menu is menu
        menu.actions()[0].trigger()
        menu.actions()[2].trigger()
        assert shown == [("About thing", "thing 1.0")] and opened == ["guide"]

    def test_a_plain_widget_passes_its_own_bar(self, qtbot):
        from PySide6.QtWidgets import QMenuBar

        widget = QWidget()
        qtbot.addWidget(widget)
        bar = QMenuBar(widget)
        menu = help_menu.install_help_menu(widget, about_title="About", about_text=str, menu_bar=bar)
        assert bar.actions()[0].menu() is menu
