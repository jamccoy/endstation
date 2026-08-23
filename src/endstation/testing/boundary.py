"""Enforcing that the pure layer stays pure.

A project keeps its toolkit imports inside one subpackage so the rest can be
tested without a display. That is a promise, and a promise nothing checks is a
convention -- it survives exactly until someone needs "just a QColor" in a
module that was pure, and the headless tests quietly stop running.

**A subprocess import, not an AST scan.** Both forms existed across the
projects this was drawn from, and the subprocess one is strictly better: it
catches *transitive* imports. A pure module that grows an innocent import of
something which itself pulls in Qt passes a source scan and fails here, which is
the right way round. The cost is one interpreter start per module, which is
nothing next to a suite that already builds windows.

:func:`assert_qt_free` is the general form -- it takes the forbidden top-level
names, so the same helper covers "no Qt in the core" and "no matplotlib in the
CLI".
"""

from __future__ import annotations

import subprocess
import sys
from typing import Iterable, Sequence

__all__ = ["TOOLKITS", "assert_import_free", "assert_qt_free", "leaked_imports"]

#: Every Qt binding a stray import might reach for.
TOOLKITS: tuple[str, ...] = ("PySide6", "PySide2", "PyQt5", "PyQt6")

_PROBE = """
import sys, {module}
forbidden = {forbidden!r}
print('\\n'.join(sorted({{n.split('.')[0] for n in sys.modules}} & set(forbidden))))
"""


def leaked_imports(module: str, forbidden: Sequence[str]) -> tuple[str, ...]:
    """Import ``module`` in a fresh interpreter; return which ``forbidden`` it reached.

    Raises :class:`RuntimeError` if the module cannot be imported at all -- that
    is a different failure from a leak, and reporting it as one would send a
    maintainer looking for an import that is not there.
    """
    probe = subprocess.run(
        [sys.executable, "-c", _PROBE.format(module=module,
                                             forbidden=tuple(forbidden))],
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        raise RuntimeError(f"{module} failed to import:\n{probe.stderr}")
    return tuple(probe.stdout.split())


def assert_import_free(
    modules: Iterable[str],
    forbidden: Sequence[str],
    *,
    reason: str = "",
) -> None:
    """Assert that none of ``modules`` reaches any of ``forbidden``.

    ``reason`` is appended to the failure so the message says *why* the boundary
    exists, not merely that it was crossed.
    """
    modules = tuple(modules)
    assert modules, "no modules given; the check would pass vacuously"

    offenders = {}
    for module in modules:
        leaked = leaked_imports(module, forbidden)
        if leaked:
            offenders[module] = leaked

    if offenders:
        lines = [f"  {m} pulled in {', '.join(v)}" for m, v in offenders.items()]
        message = "these modules were supposed to stay clean:\n" + "\n".join(lines)
        raise AssertionError(f"{message}\n{reason}" if reason else message)


def assert_qt_free(modules: Iterable[str], *, reason: str = "") -> None:
    """Assert that none of ``modules`` imports a Qt binding, directly or otherwise."""
    assert_import_free(
        modules,
        TOOLKITS,
        reason=reason or (
            "Only the widget subpackage may import a toolkit -- everything else "
            "is tested headlessly, and that stops being true the moment one of "
            "these does."
        ),
    )
