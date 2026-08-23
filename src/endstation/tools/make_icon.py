#!/usr/bin/env python
"""Render a project's artwork into a macOS ``.icns``.

    endstation-icon --module mypkg.gui.icon --output resources/MyApp.icns

The artwork is **drawn by the project**, not stored here: each project exposes a
module with a ``render(path, size)`` function -- usually matplotlib patches --
and this turns its 1024 px master into the ten-variant iconset macOS wants, then
packs it with ``iconutil``.

Generating rather than storing keeps the icon reproducible and editable in the
same language as the rest of the project, and it is why there is no binary asset
in any of these repositories.

The ten ``sips`` calls and the exact filenames are the whole content of this
module, and they existed verbatim in three projects. ``iconutil`` is fussy about
those names: get one wrong and it fails with a message that does not say which.
"""

from __future__ import annotations

import argparse
import importlib
import subprocess
import sys
import tempfile
from pathlib import Path

__all__ = ["VARIANTS", "build_icns", "render_master"]

#: macOS expects exactly these, and ``iconutil`` is fussy about the names.
VARIANTS: tuple[tuple[int, str], ...] = (
    (16, "icon_16x16.png"),
    (32, "icon_16x16@2x.png"),
    (32, "icon_32x32.png"),
    (64, "icon_32x32@2x.png"),
    (128, "icon_128x128.png"),
    (256, "icon_128x128@2x.png"),
    (256, "icon_256x256.png"),
    (512, "icon_256x256@2x.png"),
    (512, "icon_512x512.png"),
    (1024, "icon_512x512@2x.png"),
)


def _require_macos_tools() -> None:
    if sys.platform != "darwin":
        raise SystemExit("iconutil is macOS-only; skipping the .icns build")
    import shutil

    missing = [t for t in ("sips", "iconutil") if shutil.which(t) is None]
    if missing:
        raise SystemExit(
            f"{', '.join(missing)} not found -- expected to ship with macOS"
        )


def render_master(module_name: str, path: Path, size: int = 1024) -> Path:
    """Call the project's own ``render(path, size)``.

    The module is imported by name so the project keeps ownership of its
    artwork; this only knows the calling convention.
    """
    module = importlib.import_module(module_name)
    render = getattr(module, "render", None)
    if render is None:
        raise SystemExit(
            f"{module_name} has no render(path, size) function.\n"
            "An icon module should draw the artwork and write a square PNG."
        )
    render(str(path), size=size)
    if not path.exists():  # pragma: no cover - a misbehaving render()
        raise SystemExit(f"{module_name}.render did not write {path}")
    return path


def build_icns(
    module_name: str,
    output: Path,
    *,
    preview: bool = True,
) -> Path:
    """Render, downsample, and pack. Returns the ``.icns`` path.

    ``preview`` also writes a 512 px PNG alongside, for a README or anything
    that is not macOS.
    """
    _require_macos_tools()
    output = Path(output)

    with tempfile.TemporaryDirectory() as scratch:
        master = render_master(module_name, Path(scratch) / "master.png")

        iconset = Path(scratch) / f"{output.stem}.iconset"
        iconset.mkdir()
        for pixels, name in VARIANTS:
            subprocess.run(
                ["sips", "-z", str(pixels), str(pixels), str(master),
                 "--out", str(iconset / name)],
                check=True, capture_output=True,
            )

        output.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(output)],
            check=True, capture_output=True,
        )

        if preview:
            subprocess.run(
                ["sips", "-z", "512", "512", str(master),
                 "--out", str(output.with_suffix(".png"))],
                check=True, capture_output=True,
            )

    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--module", required=True,
        help="import path of a module exposing render(path, size), "
             "e.g. mypkg.gui.icon",
    )
    parser.add_argument(
        "--output", required=True, type=Path,
        help="where to write the .icns",
    )
    parser.add_argument(
        "--no-preview", action="store_true",
        help="skip the 512 px PNG written alongside",
    )
    args = parser.parse_args(argv)

    icns = build_icns(args.module, args.output, preview=not args.no_preview)
    print(f"wrote {icns} ({icns.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
