"""Launchers: a macOS ``.app`` and its icon, and a Windows shortcut and its icon.

The bundles are not frozen: there is no PyInstaller and no embedded
interpreter. A bundle here consists of three small files (a plist, a shell
stub, and an icon), which is enough for a Dock icon and a double-clickable
launcher, and it takes a second to rebuild.

The bundle is a build artifact, and this generator is what is versioned. The
stub hard-codes an absolute path to one checkout's virtualenv, which is wrong
on any other machine, so committing the generated ``.app`` would commit a
launcher that works nowhere else.

The macOS tools shell out to ``sips`` and ``iconutil``, which ship with macOS.
The Windows one, :mod:`~endstation.tools.make_shortcut`, writes the ``.lnk``
through Windows PowerShell, which ships with Windows, and packs the ``.ico``
with Pillow, which matplotlib already requires. So nothing is installed for
either, and each entry point checks its platform before doing any work.
"""

from __future__ import annotations

__all__ = ["App", "Shortcut", "build_app", "build_icns", "build_ico", "write_shortcut"]


def __getattr__(name: str):
    # Deferred so `import endstation.tools` costs nothing and does not drag in
    # matplotlib, which only the icon renderer needs.
    if name in ("build_icns",):
        from .make_icon import build_icns

        return build_icns
    if name in ("App", "build_app"):
        from .make_app import App, build_app

        return {"App": App, "build_app": build_app}[name]
    if name in ("Shortcut", "build_ico", "write_shortcut"):
        from . import make_shortcut

        return getattr(make_shortcut, name)
    raise AttributeError(name)
