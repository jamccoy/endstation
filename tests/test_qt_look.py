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
    yield tmp_path / "s.ini"
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

    def test_current_without_a_manager_is_the_default(self, store):
        assert theming.current() is theme.LIGHT
        assert theming.current(theme.DARK) is theme.DARK


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
