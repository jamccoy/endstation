"""Finding a checkout, and finding research data that is not in it.

Every project here solved these two problems separately.

The repository is located by walking upward for a marker file. The search
should look for ``pyproject.toml`` and not for a ``data`` directory, a lesson
already learned once: searching for a directory that legitimately exists in
several places finds the wrong one, and does so silently.

The data is kept outside the checkout. Raw AFM scans, synchrotron beamline
trees and instrument reference files are large, private, or belong to a
research group, and committing them is a mistake that is hard to undo. They are
therefore reached through an environment variable with a documented default.
As a consequence a clean clone has no data, and this is not a failure; it is
the normal state for CI and for anyone who did not collect the data. Code must
therefore be able to ask whether the data is present without raising, and
tests must skip cleanly and state which variable would enable them.

The most important rule is that a missing data root is reported by name.
``FileNotFoundError: [Errno 2]`` on a path the user never typed gives no
indication of what to do, whereas naming the variable and the path it resolved
to makes the fix a single line.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["MissingData", "data_root", "find_data", "find_project_root", "require_dir"]

#: Files that mark the top of a checkout, most specific first.
DEFAULT_MARKERS = ("pyproject.toml", "setup.py", ".git")


class MissingData(FileNotFoundError):
    """A configured data root does not exist, and the message says which one."""


def find_project_root(
    start: Path | str | None = None,
    *,
    markers: tuple[str, ...] = DEFAULT_MARKERS,
) -> Path:
    """Walk upward from ``start`` looking for a project marker.

    ``start`` defaults to the caller's current working directory. If no marker
    is found the working directory is returned without raising, because a
    package imported from a wheel has no checkout above it, and that is a
    legitimate way to be installed.

    Markers are checked in order at each level, so a nested checkout resolves to
    the innermost ``pyproject.toml`` rather than to an outer ``.git``.
    """
    here = Path(start).resolve() if start is not None else Path.cwd().resolve()
    if here.is_file():
        here = here.parent

    for directory in (here, *here.parents):
        for marker in markers:
            if (directory / marker).exists():
                return directory
    return Path.cwd().resolve()


def data_root(env_var: str, default: Path | str) -> Path:
    """Resolve a research-data root from the environment, with a default.

    This function does not check that the directory exists; that is the job of
    :func:`require_dir`. Keeping the two separate allows a caller to ask where
    the directory would be (to name it in a skip message or an error) without
    having to handle an exception first.

    ``~`` is expanded, so a default of ``"~/Documents/ALS"`` and an exported
    ``ALS_DATA_ROOT=~/elsewhere`` both behave the way a user expects.
    """
    raw = os.environ.get(env_var) or str(default)
    return Path(raw).expanduser()


def require_dir(
    path: Path,
    *,
    env_var: str | None = None,
    hint: str | None = None,
) -> Path:
    """Return ``path`` if it is a directory, else raise a message worth reading.

    Parameters
    ----------
    env_var
        The variable that would override this location. Named in the message,
        because "set X to point somewhere else" is the actual fix.
    hint
        Where to read more, typically a docs path. It is optional because not
        every project has a data document.
    """
    if path.is_dir():
        return path

    lines = [f"data directory not found: {path}"]
    if env_var:
        lines.append(f"Set {env_var} to point at it.")
    if hint:
        lines.append(f"See {hint}.")
    raise MissingData("\n".join(lines))


def find_data(
    env_var: str,
    default: Path | str,
    *,
    hint: str | None = None,
) -> Path:
    """:func:`data_root` then :func:`require_dir`, for the common case."""
    return require_dir(data_root(env_var, default), env_var=env_var, hint=hint)
