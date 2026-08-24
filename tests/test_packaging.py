"""What the distribution promises, checked against the code.

Packaging metadata is the one part of a project that no other test exercises:
it is read by pip, not by Python, so an extra can be wrong for months while
every test passes. Both failures below were real.
"""

import tomllib
from pathlib import Path

import pytest

PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"
SRC = Path(__file__).parent.parent / "src" / "endstation"


@pytest.fixture(scope="module")
def config():
    return tomllib.loads(PYPROJECT.read_text())


def _imports_under(subpackage: str) -> set[str]:
    """Top-level third-party names imported anywhere under ``subpackage``.

    Text scan rather than an import: the point is what the *source* asks for,
    including the deferred imports that make a broken extra survive an import
    check and fail only on use -- which is how this got missed.
    """
    import re

    found: set[str] = set()
    pattern = re.compile(r"^\s*(?:from|import)\s+(matplotlib|PySide6|numpy|shiboken6)\b",
                         re.MULTILINE)
    for path in (SRC / subpackage).rglob("*.py"):
        found.update(pattern.findall(path.read_text()))
    return found


def test_the_qt_extra_covers_what_the_qt_package_imports(config):
    """`endstation.qt.canvas` embeds a figure; `use_qt_backend` pins a backend.

    The extra listed only PySide6, so `pip install endstation[qt]` produced a
    FigurePane that raised on construction -- with a bare ModuleNotFoundError,
    the exact failure this package exists to replace.

    shiboken6 is exempt: it ships with PySide6 rather than being declared.
    """
    declared = " ".join(config["project"]["optional-dependencies"]["qt"])
    for module in _imports_under("qt") - {"shiboken6"}:
        assert module.lower() in declared.lower(), (
            f"endstation.qt imports {module}, which the `qt` extra does not declare"
        )


def test_the_docs_extra_covers_what_the_docs_package_imports(config):
    declared = " ".join(config["project"]["optional-dependencies"]["docs"])
    for module in _imports_under("docs"):
        assert module.lower() in declared.lower(), (
            f"endstation.docs imports {module}, which `docs` does not declare"
        )


def test_the_core_declares_no_dependencies(config):
    """The rule the whole package is shaped around."""
    assert config["project"]["dependencies"] == []


def test_the_version_has_one_source(config):
    """Two literals drift, and the one that drifts is the one nobody looks at."""
    import endstation

    assert "version" in config["project"].get("dynamic", []), (
        "version should be dynamic, read from endstation.__version__"
    )
    from importlib.metadata import version

    assert version("endstation") == endstation.__version__


def test_the_typing_marker_ships():
    """PEP 561. Without it a consumer's type checker ignores every annotation
    here -- they exist and do nothing, which is worse than not having them."""
    assert (SRC / "py.typed").is_file()


def test_the_typing_marker_is_declared_as_package_data(config):
    """Present in the checkout is not the same as present in the wheel."""
    package_data = config["tool"]["setuptools"]["package-data"]
    assert "py.typed" in " ".join(package_data.get("endstation", []))


def test_the_python_floor_matches_the_consumers(config):
    """eblfrac declares >=3.10. A shared package must not raise its consumers'
    floor, which is the whole reason this is not 3.12."""
    assert config["project"]["requires-python"] == ">=3.10"


def test_copier_finds_the_template_where_a_url_points(config):
    """`copier copy gh:jamccoy/endstation` looks for copier.yml at the *root*.

    There is no CLI flag to point it at a subdirectory, so a copier.yml buried
    in `template/` makes the template unreachable by the command the README
    gives -- which is how it shipped.
    """
    root = PYPROJECT.parent
    assert (root / "copier.yml").is_file(), "copier.yml must sit at the repo root"

    import yaml

    spec = yaml.safe_load((root / "copier.yml").read_text())
    subdirectory = spec["_subdirectory"]
    assert (root / subdirectory).is_dir(), f"_subdirectory {subdirectory!r} does not exist"


def test_the_readme_documents_a_command_that_resolves():
    """The README's copier line must not name a flag copier does not have."""
    readme = (PYPROJECT.parent / "README.md").read_text()
    line = next(x for x in readme.splitlines() if "copier copy" in x)
    assert "--subdirectory" not in line, (
        "copier has no --subdirectory flag; the mechanism is _subdirectory in copier.yml"
    )
