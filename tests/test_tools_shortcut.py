"""The Windows shortcut and its icon (endstation-shortcut)."""

import sys
import textwrap
from pathlib import Path

import pytest

from endstation.tools.make_shortcut import (
    ICO_SIZES,
    Shortcut,
    build_ico,
    check_shortcut,
    main,
    read_shortcut,
    write_shortcut,
)

windows_only = pytest.mark.skipif(
    sys.platform != "win32", reason="Windows shortcuts are Windows-only"
)


@pytest.fixture
def icon_module(tmp_path, monkeypatch):
    """A project icon module: render(path, size) writes a square PNG."""
    pytest.importorskip("PIL")
    package = tmp_path / "demoicon"
    package.mkdir()
    (package / "__init__.py").write_text(textwrap.dedent("""
        from PIL import Image

        def render(path, size=1024):
            Image.new("RGBA", (size, size), (200, 60, 20, 255)).save(path)
    """), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    return "demoicon"


# -- identity ---------------------------------------------------------------


def test_the_shortcut_runs_the_module_with_dash_m():
    """A [project.scripts] .exe is a console program and keeps a terminal open."""
    s = Shortcut(name="demo", python=Path("v/Scripts/pythonw.exe"), module="demo.gui")
    assert s.arguments == "-m demo.gui"


def test_it_starts_in_the_virtualenv_root():
    """-m puts the working directory first on sys.path, so it must not shadow."""
    s = Shortcut(name="demo", python=Path("apps/demo/venv/Scripts/pythonw.exe"),
                 module="demo.gui")
    assert s.working_directory == Path("apps/demo/venv")


# -- the icon ---------------------------------------------------------------


def test_the_ico_carries_every_size_explorer_asks_for(icon_module, tmp_path):
    from PIL import Image

    ico = build_ico(icon_module, tmp_path / "out" / "demo.ico")
    with Image.open(ico) as image:
        assert set(image.info["sizes"]) == {(s, s) for s in ICO_SIZES}
    assert not (tmp_path / "out" / "demo.ico.partial").exists()


def test_a_module_without_render_is_refused(tmp_path, monkeypatch):
    pytest.importorskip("PIL")
    (tmp_path / "noart.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(SystemExit, match="render"):
        build_ico("noart", tmp_path / "x.ico")


# -- writing and checking (Windows) ------------------------------------------


@pytest.fixture
def venv(tmp_path):
    """A stand-in virtualenv. Writing a shortcut needs only that the target exists."""
    scripts = tmp_path / "apps" / "demo" / "venv" / "Scripts"
    scripts.mkdir(parents=True)
    pythonw = scripts / "pythonw.exe"
    pythonw.write_bytes(b"")
    return pythonw


@windows_only
def test_a_written_shortcut_reads_back(venv, tmp_path, icon_module):
    ico = build_ico(icon_module, tmp_path / "demo.ico")
    s = Shortcut(name="demo app", python=venv, module="demo.gui", icon=ico,
                 description="Demo, from PyPI")
    lnk = write_shortcut(s, tmp_path / "desk")
    assert lnk == tmp_path / "desk" / "demo app.lnk"
    fields = read_shortcut(lnk)
    assert Path(fields["target"]) == venv
    assert fields["arguments"] == "-m demo.gui"
    assert Path(fields["working_directory"]) == venv.parent.parent
    assert fields["icon"] == f"{ico},0"
    assert fields["description"] == "Demo, from PyPI"


@windows_only
def test_rewriting_replaces_the_old_shortcut(venv, tmp_path):
    write_shortcut(Shortcut("demo", venv, "old.gui"), tmp_path)
    write_shortcut(Shortcut("demo", venv, "new.gui"), tmp_path)
    assert read_shortcut(tmp_path / "demo.lnk")["arguments"] == "-m new.gui"


@windows_only
def test_a_path_with_quotes_and_dollars_survives(venv, tmp_path):
    """Values reach PowerShell through the environment, never the script text."""
    odd = tmp_path / "it's $HOME `x`"
    lnk = write_shortcut(Shortcut("demo", venv, "demo.gui"), odd)
    assert lnk.is_file()


@windows_only
def test_a_missing_interpreter_is_refused(tmp_path):
    with pytest.raises(SystemExit, match="virtualenv"):
        write_shortcut(Shortcut("demo", tmp_path / "pythonw.exe", "demo.gui"), tmp_path)


@windows_only
def test_check_reports_a_moved_virtualenv_and_a_missing_icon(venv, tmp_path, icon_module):
    ico = build_ico(icon_module, tmp_path / "demo.ico")
    lnk = write_shortcut(Shortcut("demo", venv, "demo.gui", icon=ico), tmp_path)
    ico.unlink()
    venv.unlink()
    problems = check_shortcut(lnk)
    assert any("interpreter no longer exists" in p for p in problems)
    assert any("icon is missing" in p for p in problems)


@windows_only
def test_check_reports_a_module_the_interpreter_cannot_find(tmp_path):
    """Uses the real interpreter, so the import probe actually runs."""
    real = Path(sys.executable).with_name("pythonw.exe")
    if not real.is_file():
        pytest.skip("no pythonw.exe beside this interpreter")
    good = write_shortcut(Shortcut("good", real, "json"), tmp_path)
    bad = write_shortcut(Shortcut("bad", real, "no_such_module_here"), tmp_path)
    assert check_shortcut(good) == []
    assert check_shortcut(bad) == ["no_such_module_here is not installed in that virtualenv"]


@windows_only
def test_the_command_writes_icon_and_shortcut(venv, tmp_path, icon_module, capsys):
    status = main(["--name", "demo", "--module", "demo.gui",
                   "--icon-module", icon_module, "--python", str(venv),
                   "--dest", str(tmp_path / "desk")])
    assert status == 0
    ico = venv.parent.parent.parent / "demo.ico"
    assert ico.is_file()
    assert read_shortcut(tmp_path / "desk" / "demo.lnk")["icon"] == f"{ico},0"


def test_check_of_a_missing_file_says_so(tmp_path):
    assert check_shortcut(tmp_path / "absent.lnk") == [f"{tmp_path / 'absent.lnk'} does not exist"]


def test_icon_and_icon_module_are_alternatives(tmp_path):
    with pytest.raises(SystemExit):
        main(["--name", "d", "--module", "m", "--icon", "x.ico", "--icon-module", "y"])
