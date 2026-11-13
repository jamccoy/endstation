"""Writing a file so that it is either the old one or the new one, never half.

An export written with a plain ``open(path, "w")`` is truncated the moment it
opens, so a crash, a full disk or an exception part-way through leaves a short
file where a good one was. :func:`atomic_open` writes to a temporary file in
the same directory and moves it over the target only when the ``with`` block
finishes cleanly, with ``os.replace``, which is atomic on one filesystem on
every platform Python supports. On failure the temporary file is removed and
the target is untouched.

Core module: standard library only.
"""

from __future__ import annotations

import contextlib
import os
import secrets
from collections.abc import Iterator
from pathlib import Path
from typing import IO

__all__ = ["atomic_open", "atomic_write"]


@contextlib.contextmanager
def atomic_open(
    path: "str | os.PathLike[str]",
    mode: str = "w",
    *,
    encoding: str | None = None,
    newline: str | None = None,
) -> Iterator[IO]:
    """Open ``path`` for writing; it appears only if the block completes.

    ``mode`` is ``"w"`` or ``"wb"``; ``encoding`` and ``newline`` are passed
    to ``open`` as usual (text mode defaults to UTF-8 here, not the locale's
    encoding). The file is flushed and synced before the replace, so the new
    contents are on disk when the name points at them.
    """
    if mode not in ("w", "wb"):
        raise ValueError(f"atomic_open writes a whole file; mode must be 'w' or 'wb', not {mode!r}")
    target = Path(path)
    if mode == "w" and encoding is None:
        encoding = "utf-8"
    fd, temporary = _create_beside(target)
    try:
        with open(fd, mode, encoding=encoding, newline=newline) as handle:
            yield handle
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


def _create_beside(target: Path) -> tuple[int, str]:
    """A new temporary file next to ``target``, created with mode 0o666.

    Not ``tempfile.mkstemp``, which creates 0o600: the replace keeps the
    temporary file's mode, so every export would become private to its
    owner. ``os.open`` with 0o666 lets the umask decide, as ``open`` does.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    for _ in range(100):
        name = target.parent / f".{target.name}.{secrets.token_hex(4)}.tmp"
        try:
            return os.open(name, flags, 0o666), str(name)
        except FileExistsError:
            continue
    raise FileExistsError(f"could not create a temporary file beside {target}")


def atomic_write(
    path: "str | os.PathLike[str]",
    data: "str | bytes",
    *,
    encoding: str = "utf-8",
    newline: str | None = None,
) -> None:
    """Write ``data`` to ``path`` through :func:`atomic_open`."""
    if isinstance(data, bytes):
        with atomic_open(path, "wb") as handle:
            handle.write(data)
    else:
        with atomic_open(path, "w", encoding=encoding, newline=newline) as handle:
            handle.write(data)
