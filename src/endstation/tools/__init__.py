"""Building a macOS ``.app`` and its icon.

Not frozen bundles. No PyInstaller, no embedded interpreter. A bundle here is
three small files -- a plist, a shell stub, and an icon -- which is enough for a
Dock icon and a double-clickable launcher, and takes a second to rebuild.

**The bundle is a build artifact; this is what is versioned.** The stub
hard-codes an absolute path to one checkout's virtualenv, which is wrong on any
other machine, so committing the generated ``.app`` would commit a launcher that
works nowhere else.

These are developer tools that shell out to ``sips`` and ``iconutil``. Both ship
with macOS, so there is nothing to install -- and nothing here runs anywhere
else, which the entry points check before doing any work.
"""

from __future__ import annotations

__all__ = ["App", "build_app", "build_icns"]


def __getattr__(name: str):
    # Deferred so `import endstation.tools` costs nothing and does not drag in
    # matplotlib, which only the icon renderer needs.
    if name in ("build_icns",):
        from .make_icon import build_icns

        return build_icns
    if name in ("App", "build_app"):
        from .make_app import App, build_app

        return {"App": App, "build_app": build_app}[name]
    raise AttributeError(name)
