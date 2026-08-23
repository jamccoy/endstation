"""Finding a checkout, and finding research data that is not in it.

Two problems that every project here solved separately.

**Where is the repository?** Walk up for a marker file. The trap, learned once
already: search for ``pyproject.toml``, not for a ``data`` directory. Searching
for a directory that legitimately exists in several places finds the wrong one,
and finds it silently.

**Where is the data?** Not in the checkout. Raw AFM scans, synchrotron beamline
trees and instrument reference files are large, private, or belong to a research
group, and committing them is a mistake that is hard to undo -- so they live
outside, reached through an environment variable with a documented default. The
consequence is that a clean clone has no data, which is not a failure: it is the
normal state for CI and for anyone who did not collect it. Code must therefore
be able to *ask* whether the data is present without raising, and tests must
skip cleanly and say which variable would enable them.

The rule that makes this safe rather than merely convenient: **a missing data
root is reported by name.** ``FileNotFoundError: [Errno 2]`` on a path the user
never typed is unactionable; naming the variable and the path it resolved to
turns it into a one-line fix.
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
    is found the working directory is returned rather than raising: a package
    imported from a wheel has no checkout above it, and that is a legitimate
    way to be installed, not an error.

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

    Does **not** check that the directory exists -- that is
    :func:`require_dir`'s job, and separating them is what lets a caller ask
    "where would it be?" (to name it in a skip message or an error) without
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
        Where to read more -- a docs path, typically. Optional, because not
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
