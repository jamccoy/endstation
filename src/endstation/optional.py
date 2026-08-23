"""Optional dependencies that explain themselves when they are missing.

``ModuleNotFoundError: No module named 'PySide6'`` tells a user nothing about
what to do, and a missing extra is the single most likely first-run failure for
anyone who installed a package's core distribution. Every project this was
drawn from had written its own version of the same fix, with the same opening
sentence in the docstring; this is that fix, once.

Two shapes, because the projects genuinely need both:

:func:`require_extra` is a **check**, for the moment before a toolkit is
imported. It uses :func:`importlib.util.find_spec` rather than an import, for
two reasons: checking availability should not cost a full matplotlib or Qt
import in the case where the dependency *is* present, and the caller is often a
module that is forbidden from importing the toolkit at all (see
:mod:`endstation.testing.boundary`). A console-script entry point should call
it first, so a missing extra produces an install instruction rather than a
traceback naming a package the user never asked for.

:func:`optional_module` is a **proxy**, for a library that only some functions
need. Importing such a dependency at module scope means one missing package
breaks every function in the module, including the ones that never touch it.
The proxy defers the import until an attribute is actually used, so the module
imports cleanly and only the functions that genuinely need it raise.

Neither is a fallback. Nothing here degrades to a stub that silently does
nothing -- a missing dependency has to be loud, it just has to be loud in a way
that names the fix.
"""

from __future__ import annotations

from importlib.util import find_spec
from typing import Any

__all__ = ["MissingExtra", "missing_extra_message", "require_extra", "optional_module"]


class MissingExtra(ModuleNotFoundError):
    """An optional dependency is absent, and the message says how to install it.

    Derives from :class:`ModuleNotFoundError` so that callers already writing
    ``except ImportError`` keep working, and so an entry point that lets this
    escape still exits with something a user can read.
    """


def missing_extra_message(
    module: str,
    extra: str,
    *,
    package: str | None = None,
    still_works: str | None = None,
) -> str:
    """Compose the text :func:`require_extra` raises.

    Separated out because the projects downstream assert on this string -- both
    that it names the module and that it names the extra -- and a test should
    not have to trigger the failure to read it.

    ``still_works`` is the sentence that keeps this from reading as a fatal
    error. A user who wanted only the analysis, the exporter or the CLI needs
    to know that what they wanted is fine; without it, a missing GUI toolkit
    looks like a broken install.

    **The command is quoted, and the quotes are load-bearing.** Square brackets
    are glob characters: zsh -- the default shell on macOS, where all of this
    runs -- answers unquoted ``pip install .[gui]`` with ``no matches found``,
    which is a worse first experience than the ImportError this replaced. An
    editable install is offered for the no-``package`` case because that is the
    situation a developer in a checkout is actually in.
    """
    if package:
        command = f"pip install '{package}[{extra}]'"
    else:
        command = f"pip install -e '.[{extra}]'"
    lines = [
        f"this feature needs {module}, which is an optional extra.",
        "Install it with:",
        "",
        f"    {command}",
        "",
    ]
    if still_works:
        lines.append(still_works)
    return "\n".join(lines)


def require_extra(
    module: str,
    extra: str,
    *,
    package: str | None = None,
    still_works: str | None = None,
) -> None:
    """Raise something useful if ``module`` is not importable.

    Parameters
    ----------
    module
        The top-level import name to look for, e.g. ``"PySide6"``.
    extra
        The extra that provides it, e.g. ``"gui"``.
    package
        Distribution name, so the message can say ``pip install mypkg[gui]``.
        Omitted for an editable checkout, where ``pip install '.[gui]'`` is what
        a developer actually runs.
    still_works
        One sentence naming what does not need this extra.

    Uses ``find_spec`` rather than importing, so this is safe to call from a
    module that must itself stay toolkit-free.
    """
    # `find_spec` raises rather than returning None when a *parent* package is
    # missing, which is the same answer for our purposes.
    try:
        found = find_spec(module) is not None
    except (ImportError, ValueError):  # pragma: no cover - malformed install
        found = False

    if not found:
        raise MissingExtra(
            missing_extra_message(
                module, extra, package=package, still_works=still_works
            )
        )


class _OptionalModule:
    """Proxy that imports ``name`` on first attribute access."""

    def __init__(self, name: str, extra: str, package: str | None,
                 still_works: str | None) -> None:
        # Written through `object.__setattr__`-style plain assignment is fine
        # here because `__getattr__` only fires for attributes that are *not*
        # found normally, and these are.
        self._name = name
        self._extra = extra
        self._package = package
        self._still_works = still_works
        self._module: Any = None

    def __getattr__(self, attr: str) -> Any:
        # Guard against recursion on our own private attributes: during
        # unpickling or early construction they may not be set yet, and
        # `__getattr__` would then ask for `_module` to resolve `_module`.
        if attr.startswith("_"):
            raise AttributeError(attr)

        if self._module is None:
            try:
                self._module = __import__(self._name, fromlist=["__name__"])
            except ImportError as err:
                raise MissingExtra(
                    missing_extra_message(
                        self._name,
                        self._extra,
                        package=self._package,
                        still_works=self._still_works,
                    )
                ) from err
        return getattr(self._module, attr)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        state = "loaded" if self._module is not None else "not yet imported"
        return f"<optional module {self._name!r} ({state})>"


def optional_module(
    name: str,
    extra: str,
    *,
    package: str | None = None,
    still_works: str | None = None,
) -> Any:
    """Return a lazy proxy for ``name``.

    Bind it at module scope in place of the import::

        astropy = optional_module("astropy", "trapezoid", package="als_eff_meas")

    The import happens on first attribute access, so a module using this stays
    importable -- and its other functions stay usable -- without the dependency.
    """
    return _OptionalModule(name, extra, package, still_works)
