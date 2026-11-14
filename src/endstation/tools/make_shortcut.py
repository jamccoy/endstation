#!/usr/bin/env python
r"""Write a Windows shortcut, with its icon, that launches a project's GUI.

    venv\Scripts\endstation-shortcut --name gratinglab \
        --module gratinglab.gui.launcher --icon-module gratinglab.gui.icon

The Windows counterpart of ``endstation-app`` and ``endstation-icon`` in one
command. Run it with the Python of the virtualenv the shortcut should launch:
that interpreter's ``pythonw.exe`` is the shortcut's target, and the icon is
drawn by importing the project's icon module in this same process.

What it writes:

* ``<name>.ico`` beside the virtualenv, packed from the project's own
  ``render(path, size)`` (see :mod:`endstation.tools.make_icon`) at the seven
  sizes Explorer asks for. Pillow does the packing; matplotlib already
  requires it, so any project that draws its icon with matplotlib has it.
* ``<name>.lnk`` on the Desktop by default, or in the Start menu with
  ``--where start-menu``. The Desktop is the folder Windows reports, which on
  a machine with OneDrive backup is under ``OneDrive`` rather than ``~``.

The shortcut runs ``pythonw.exe -m <module>`` rather than a console script's
``.exe``. A script declared under ``[project.scripts]`` is a console program,
so its ``.exe`` opens a terminal window that stays for as long as the GUI
does. ``pythonw.exe`` has no console.

The working directory is the virtualenv's own folder. ``-m`` puts the working
directory first on ``sys.path``, so a folder holding a directory named like
the package would shadow the installed one; a virtualenv's root holds only
``Lib``, ``Scripts``, ``Include`` and ``pyvenv.cfg``.

Upgrading is pip's job, not this tool's. After ``pip install --upgrade`` the
shortcut still points at the same ``pythonw.exe`` and keeps working; re-run
this only to redraw the icon. ``--check`` reports a shortcut whose
interpreter, icon or module has gone, which is how one breaks when the
virtualenv is moved or rebuilt.

The ``.lnk`` is written through the ``WScript.Shell`` COM object in Windows
PowerShell, which ships with Windows, so nothing is installed to write it.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .make_icon import render_master

__all__ = [
    "ICO_SIZES",
    "Shortcut",
    "build_ico",
    "check_shortcut",
    "read_shortcut",
    "special_folder",
    "write_shortcut",
]

#: The sizes Explorer picks from, for list views up to extra-large icons.
ICO_SIZES: tuple[int, ...] = (16, 24, 32, 48, 64, 128, 256)

#: Where ``--where`` puts the shortcut: .NET ``SpecialFolder`` names.
FOLDERS = {"desktop": "Desktop", "start-menu": "Programs"}


@dataclass(frozen=True)
class Shortcut:
    """What a shortcut launches and how it looks.

    ``python`` is the ``pythonw.exe`` to run, and ``module`` what it runs with
    ``-m``. ``icon`` is an ``.ico``; without one Explorer shows Python's.
    """

    name: str
    python: Path
    module: str
    icon: Path | None = None
    description: str = ""

    @property
    def arguments(self) -> str:
        return f"-m {self.module}"

    @property
    def working_directory(self) -> Path:
        # Scripts\pythonw.exe -> the virtualenv's root. See the module docstring.
        return Path(self.python).parent.parent


def _require_windows() -> None:
    if sys.platform != "win32":
        raise SystemExit("Windows shortcuts are Windows-only")


def _powershell(script: str, env: dict[str, str]) -> str:
    """Run ``script`` in Windows PowerShell with ``env`` added; return stdout.

    Values go in through the environment rather than into the script text, so
    a path holding a quote, a dollar sign or a backtick needs no escaping.
    """
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"PowerShell failed:\n{result.stderr.strip()}")
    return result.stdout


def special_folder(where: str) -> Path:
    """The folder Windows reports for ``desktop`` or ``start-menu``."""
    _require_windows()
    folder = _powershell(
        "[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
        "[Environment]::GetFolderPath($env:ES_FOLDER)",
        {"ES_FOLDER": FOLDERS[where]},
    ).strip()
    if not folder:
        raise SystemExit(f"Windows reported no {where} folder")
    return Path(folder)


def build_ico(module_name: str, output: Path) -> Path:
    """Render the project's artwork and pack it as a multi-size ``.ico``."""
    try:
        from PIL import Image
    except ImportError:
        raise SystemExit(
            "Pillow is needed to pack the .ico. It comes with matplotlib:\n"
            "    pip install matplotlib"
        ) from None
    output = Path(output)
    with tempfile.TemporaryDirectory() as scratch:
        master = render_master(module_name, Path(scratch) / "master.png")
        with Image.open(master) as image:
            square = image.convert("RGBA")
        output.parent.mkdir(parents=True, exist_ok=True)
        # Written beside the target and moved in, so a shortcut already
        # pointing at the old icon never sees a half-written one.
        partial = output.with_name(output.name + ".partial")
        square.save(partial, format="ICO", sizes=[(s, s) for s in ICO_SIZES])
        os.replace(partial, output)
    return output


_WRITE = r"""
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($env:ES_LNK)
$link.TargetPath = $env:ES_TARGET
$link.Arguments = $env:ES_ARGS
$link.WorkingDirectory = $env:ES_CWD
$link.Description = $env:ES_DESCRIPTION
if ($env:ES_ICON) { $link.IconLocation = "$($env:ES_ICON),0" }
$link.Save()
"""


def write_shortcut(shortcut: Shortcut, destination: Path) -> Path:
    """Write ``<destination>/<name>.lnk``, replacing any there. Returns its path."""
    _require_windows()
    python = Path(shortcut.python)
    if not python.is_file():
        raise SystemExit(
            f"{python} not found. Run this with the Python of the virtualenv "
            "the shortcut should launch, or pass --python."
        )
    if shortcut.icon is not None and not Path(shortcut.icon).is_file():
        raise SystemExit(f"{shortcut.icon} not found")
    lnk = Path(destination) / f"{shortcut.name}.lnk"
    lnk.parent.mkdir(parents=True, exist_ok=True)
    _powershell(_WRITE, {
        "ES_LNK": str(lnk),
        "ES_TARGET": str(python),
        "ES_ARGS": shortcut.arguments,
        "ES_CWD": str(shortcut.working_directory),
        "ES_DESCRIPTION": shortcut.description or shortcut.name,
        "ES_ICON": str(shortcut.icon) if shortcut.icon is not None else "",
    })
    return lnk


_READ = r"""
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$link = (New-Object -ComObject WScript.Shell).CreateShortcut($env:ES_LNK)
$link.TargetPath
$link.Arguments
$link.WorkingDirectory
$link.IconLocation
$link.Description
"""


def read_shortcut(lnk: Path) -> dict[str, str]:
    """A shortcut's target, arguments, working directory, icon and description."""
    _require_windows()
    lines = _powershell(_READ, {"ES_LNK": str(lnk)}).splitlines()
    keys = ("target", "arguments", "working_directory", "icon", "description")
    lines += [""] * (len(keys) - len(lines))
    return dict(zip(keys, (line.strip() for line in lines)))


def check_shortcut(lnk: Path) -> list[str]:
    """Report what is wrong with an existing shortcut. An empty list means it is fine.

    The usual breakage cannot be seen from Explorer: the virtualenv was moved,
    rebuilt or had the package uninstalled, and double-clicking does nothing,
    because ``pythonw.exe`` has no console to print the error to.
    """
    lnk = Path(lnk)
    if not lnk.is_file():
        return [f"{lnk} does not exist"]
    fields = read_shortcut(lnk)
    problems: list[str] = []

    target = Path(fields["target"]) if fields["target"] else None
    if target is None or not target.is_file():
        problems.append(f"the interpreter no longer exists: {fields['target']}")

    icon = fields["icon"].rsplit(",", 1)[0]
    if icon and not Path(icon).is_file():
        problems.append(f"the icon is missing: {icon}")

    arguments = fields["arguments"].split()
    if len(arguments) == 2 and arguments[0] == "-m" and target is not None and target.is_file():
        module = arguments[1]
        # python.exe beside pythonw.exe, so an import error can be read back.
        console = target.with_name("python.exe")
        probe = console if console.is_file() else target
        found = subprocess.run(
            [str(probe), "-c",
             "import importlib.util, sys; "
             "sys.exit(importlib.util.find_spec(sys.argv[1]) is None)", module],
            cwd=fields["working_directory"] or None,
            capture_output=True,
            check=False,
        )
        if found.returncode != 0:
            problems.append(f"{module} is not installed in that virtualenv")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--name", help="the shortcut's name, e.g. gratinglab")
    parser.add_argument("--module", help="what pythonw runs with -m, e.g. mypkg.gui.app")
    parser.add_argument("--icon-module", default=None,
                        help="module exposing render(path, size), e.g. mypkg.gui.icon")
    parser.add_argument("--icon", type=Path, default=None,
                        help="use an existing .ico instead of drawing one")
    parser.add_argument("--python", type=Path, default=None,
                        help="the pythonw.exe to launch (default: the one beside "
                             "the Python running this)")
    parser.add_argument("--where", choices=sorted(FOLDERS), default="desktop")
    parser.add_argument("--dest", type=Path, default=None,
                        help="write into this folder instead of --where's")
    parser.add_argument("--description", default="", help="the shortcut's tooltip")
    parser.add_argument("--check", type=Path, default=None,
                        help="verify an existing .lnk instead of writing one")
    args = parser.parse_args(argv)

    if args.check is not None:
        problems = check_shortcut(args.check)
        if problems:
            print(f"{args.check} has problems:")
            for problem in problems:
                print(f"  - {problem}")
            return 1
        print(f"{args.check} looks correct")
        return 0

    missing = [n for n in ("name", "module") if not getattr(args, n)]
    if missing:
        parser.error("--" + ", --".join(missing) + " required unless --check is given")
    if args.icon is not None and args.icon_module is not None:
        parser.error("--icon and --icon-module are alternatives")
    _require_windows()

    python = args.python or Path(sys.executable).with_name("pythonw.exe")
    icon = args.icon
    if args.icon_module is not None:
        # Beside the virtualenv: Scripts\pythonw.exe -> venv -> its folder.
        icon = build_ico(args.icon_module, Path(python).parent.parent.parent / f"{args.name}.ico")
        print(f"wrote {icon}")

    shortcut = Shortcut(name=args.name, python=python, module=args.module,
                        icon=icon, description=args.description)
    lnk = write_shortcut(shortcut, args.dest or special_folder(args.where))
    print(f"wrote {lnk}")
    print(f"  runs: {shortcut.python} {shortcut.arguments}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
