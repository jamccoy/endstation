"""The two new core modules: themes as data, and whole-file writes."""

import os
import sys
from dataclasses import dataclass, field

import pytest

from endstation import theme
from endstation.files import atomic_open, atomic_write


class TestTheme:
    def test_every_theme_is_in_the_menu_once_with_light_and_dark(self):
        assert list(theme.THEMES)[:2] == ["light", "dark"]
        assert all(key == t.key for key, t in theme.THEMES.items())

    def test_text_is_legible_on_every_theme(self):
        for t in theme.THEMES.values():
            assert theme.contrast(t.text, t.window) >= 4.5, t.key
            assert theme.contrast(t.ink, t.axes) >= 4.5, t.key

    def test_contrast_is_wcag(self):
        assert theme.contrast("#000000", "#ffffff") == pytest.approx(21.0)
        assert theme.contrast("#777777", "#777777") == pytest.approx(1.0)

    def test_extend_keeps_the_palette_and_adds_fields(self):
        @dataclass(frozen=True)
        class AppTheme(theme.Theme):
            diagram: dict = field(default_factory=dict)
            weight: float = 0.5

        light = AppTheme.extend(theme.LIGHT, diagram={"axis": "#888888"})
        assert isinstance(light, AppTheme)
        assert light.window == theme.LIGHT.window and light.ok == theme.LIGHT.ok
        assert light.diagram == {"axis": "#888888"} and light.weight == 0.5

    def test_rc_params_need_no_matplotlib_and_follow_the_theme(self):
        params = theme.rc_params(theme.DARK)
        assert params["axes.facecolor"] == theme.DARK.axes
        assert params["text.color"] == theme.DARK.ink
        assert all(0.0 <= c <= 1.0 for c in params["axes3d.xaxis.panecolor"])


class TestAtomicWrite:
    def test_writes_text_as_utf8_with_newline_control(self, tmp_path):
        target = tmp_path / "out.csv"
        atomic_write(target, "a,β\n1,2\n", newline="\n")
        assert target.read_bytes() == "a,β\n1,2\n".encode()

    def test_writes_bytes(self, tmp_path):
        target = tmp_path / "out.bin"
        atomic_write(target, b"\x00\x01")
        assert target.read_bytes() == b"\x00\x01"

    def test_a_failure_leaves_the_old_file_and_no_debris(self, tmp_path):
        target = tmp_path / "out.txt"
        target.write_text("old", encoding="utf-8")
        with pytest.raises(RuntimeError), atomic_open(target) as handle:
            handle.write("half")
            raise RuntimeError("disk full")
        assert target.read_text(encoding="utf-8") == "old"
        assert os.listdir(tmp_path) == ["out.txt"]

    def test_success_leaves_only_the_target(self, tmp_path):
        with atomic_open(tmp_path / "out.txt") as handle:
            handle.write("new")
        assert os.listdir(tmp_path) == ["out.txt"]

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
    def test_the_file_is_not_made_private(self, tmp_path):
        target = tmp_path / "out.txt"
        atomic_write(target, "x")
        assert target.stat().st_mode & 0o044, "group/other read follows the umask, as open() does"

    def test_only_whole_file_modes(self, tmp_path):
        with pytest.raises(ValueError), atomic_open(tmp_path / "x", "a"):
            pass
