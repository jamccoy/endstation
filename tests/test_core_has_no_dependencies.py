"""The core must import with nothing installed.

`eblfrac` declares `dependencies = []` so its fracture engine and GPF writer
install anywhere. A shared package that quietly pulled numpy in would take that
away at install time, from every downstream user, with no error to notice.

A subprocess import rather than an AST scan, because this catches *transitive*
imports too -- a pure module that grows an innocent import of something which
itself pulls in numpy would pass a source scan and fail here, which is the right
way round.
"""

import subprocess
import sys

import pytest

#: Everything a project is allowed to adopt without taking on a dependency.
CORE_MODULES = (
    "endstation",
    "endstation.optional",
    "endstation.progress",
    "endstation.forms",
    "endstation.paths",
)

#: Third-party packages the core must never reach, directly or transitively.
FORBIDDEN = ("numpy", "scipy", "matplotlib", "PySide6", "PyQt5", "PyQt6",
             "pandas", "pydantic", "markdown")


#: Printed by the subprocess, one leaked top-level package per line.
_PROBE = """
import sys, {module}
forbidden = {forbidden!r}
leaked = sorted({{n.split('.')[0] for n in sys.modules}} & set(forbidden))
print('\\n'.join(leaked))
"""


@pytest.mark.parametrize("module", CORE_MODULES)
def test_core_module_pulls_in_no_third_party_package(module):
    probe = subprocess.run(
        [sys.executable, "-c", _PROBE.format(module=module, forbidden=FORBIDDEN)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    # `check=True` would surface a CalledProcessError whose repr buries the one
    # fact that matters. Assert on the output instead, so a failure reads as the
    # sentence a maintainer needs.
    assert probe.returncode == 0, f"{module} failed to import:\n{probe.stderr}"

    leaked = probe.stdout.split()
    assert not leaked, (
        f"{module} pulled in {', '.join(leaked)}.\n"
        "The core is declared `dependencies = []` so that a project which "
        "declares the same can adopt it. Import this inside the function that "
        "needs it, or move the module behind an extra."
    )


def test_the_module_list_is_not_vacuous():
    """Guard against the parametrisation silently emptying and passing."""
    assert len(CORE_MODULES) >= 5


def test_public_api_is_importable_from_the_top_level():
    """What the core promises, in one place, so a rename cannot go unnoticed."""
    import endstation

    for name in ("require_extra", "optional_module", "MissingExtra",
                 "report", "throttled", "cancelling", "Cancelled",
                 "FieldError", "FormErrors", "ErrorCollector",
                 "find_project_root", "data_root", "find_data",
                 "require_dir", "MissingData"):
        assert hasattr(endstation, name), name
        assert name in endstation.__all__, name
