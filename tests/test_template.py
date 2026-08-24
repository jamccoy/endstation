"""The project template renders, and renders something valid.

A template that is never rendered rots quietly: a Jinja typo, a stray
GitHub-Actions `${{ }}` the renderer ate, a conditional directory that stopped
being conditional. None of that shows up until someone starts a project with it,
which is the worst moment to find out.

These render into `tmp_path` and inspect the output. They deliberately do not
`pip install` it -- that needs a network and a minute, and belongs in CI rather
than in a suite that should stay fast.
"""

from pathlib import Path

import pytest

copier = pytest.importorskip("copier", reason="copier is a dev extra")

# `tomllib` is 3.11+, and this package supports 3.10 -- caught by the CI matrix,
# which is the only place a 3.10 interpreter exists here. The tests that parse
# the generated pyproject skip there; the ones asserting on its text still run,
# so 3.10 is not left unchecked.
try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - 3.10 only
    tomllib = None

needs_tomllib = pytest.mark.skipif(
    tomllib is None, reason="tomllib is 3.11+; the text assertions still cover 3.10"
)

TEMPLATE = Path(__file__).parent.parent / "template"

GUI = dict(project_name="Demo App", package_name="demoapp",
           description="A demo", gui=True, research_data=True, min_tests=50)
LIB = dict(project_name="Demo Lib", package_name="demolib",
           description="A demo", gui=False, research_data=False,
           python_requires="3.12", min_tests=40)


def render(tmp_path: Path, data: dict) -> Path:
    target = tmp_path / "rendered"
    copier.run_copy(str(TEMPLATE), str(target), data=data,
                    defaults=True, unsafe=True, quiet=True, vcs_ref="HEAD")
    return target


@pytest.fixture(scope="module")
def gui_project(tmp_path_factory):
    return render(tmp_path_factory.mktemp("gui"), GUI)


@pytest.fixture(scope="module")
def lib_project(tmp_path_factory):
    return render(tmp_path_factory.mktemp("lib"), LIB)


# -- structure --------------------------------------------------------------


def test_the_gui_variant_has_a_widget_layer(gui_project):
    assert (gui_project / "src/demoapp/gui/qt/app.py").is_file()


def test_the_library_variant_has_no_widget_layer(lib_project):
    """A conditional directory that stopped being conditional is invisible
    until someone generates a library and finds a window in it."""
    assert not (lib_project / "src/demolib/gui").exists()


def test_both_variants_carry_the_essentials(gui_project, lib_project):
    for project in (gui_project, lib_project):
        assert (project / "pyproject.toml").is_file()
        assert (project / ".gitignore").is_file()
        assert (project / ".github/workflows/test.yml").is_file()
        assert (project / "tests/test_boundaries.py").is_file()


# -- pyproject --------------------------------------------------------------


@needs_tomllib
def test_generated_pyproject_parses(gui_project):
    data = tomllib.loads((gui_project / "pyproject.toml").read_text())
    assert data["project"]["name"] == "demo_app"
    assert "endstation>=0.1" in data["project"]["dependencies"]


@needs_tomllib
def test_the_console_script_uses_the_import_name(gui_project):
    data = tomllib.loads((gui_project / "pyproject.toml").read_text())
    assert data["project"]["scripts"]["demoapp-gui"] == "demoapp.gui:main"


@needs_tomllib
def test_the_gui_extra_exists_only_when_asked_for(gui_project, lib_project):
    gui = tomllib.loads((gui_project / "pyproject.toml").read_text())
    lib = tomllib.loads((lib_project / "pyproject.toml").read_text())
    assert "gui" in gui["project"]["optional-dependencies"]
    assert "gui" not in lib["project"]["optional-dependencies"]


def test_qt_api_is_not_declared_in_pytest_options(gui_project):
    """It is a pytest-qt option; declaring it makes the suite need the toolkit."""
    assert "qt_api =" not in (gui_project / "pyproject.toml").read_text()


def test_python_floor_is_carried_into_ruff_target(lib_project):
    text = (lib_project / "pyproject.toml").read_text()
    assert 'requires-python = ">=3.12"' in text
    assert 'target-version = "py312"' in text


# -- CI ---------------------------------------------------------------------


def test_github_expressions_survive_jinja(gui_project):
    """`${{ }}` is Actions syntax, and Jinja is very willing to eat it."""
    text = (gui_project / ".github/workflows/test.yml").read_text()
    assert "${{ github.workflow }}" in text
    assert "${{ matrix.python-version }}" in text
    assert "$${{" not in text, "double-dollar means the escaping regressed"


def test_the_workflow_is_valid_yaml(gui_project, lib_project):
    yaml = pytest.importorskip("yaml", reason="pyyaml is not installed")
    for project in (gui_project, lib_project):
        yaml.safe_load((project / ".github/workflows/test.yml").read_text())


def test_qt_system_libraries_are_installed_only_for_a_gui_project(
    gui_project, lib_project
):
    assert "libglib2.0-0t64" in (
        gui_project / ".github/workflows/test.yml"
    ).read_text()
    assert "libglib2.0-0t64" not in (
        lib_project / ".github/workflows/test.yml"
    ).read_text()


def test_the_shrinking_suite_guard_carries_the_threshold(gui_project):
    assert "expected at least 50" in (
        gui_project / ".github/workflows/test.yml"
    ).read_text()


# -- generated python -------------------------------------------------------


@pytest.mark.parametrize("relative", [
    "src/demoapp/__init__.py",
    "src/demoapp/gui/__init__.py",
    "src/demoapp/gui/qt/__init__.py",
    "src/demoapp/gui/qt/app.py",
    "tests/conftest.py",
    "tests/test_boundaries.py",
])
def test_generated_python_compiles(gui_project, relative):
    import ast

    ast.parse((gui_project / relative).read_text())


def test_the_data_fixture_names_the_variable(gui_project):
    """A suite that skips silently looks identical to one with no tests."""
    assert "DEMOAPP_DATA_DIR" in (gui_project / "tests/conftest.py").read_text()


def test_no_data_fixture_when_the_project_has_no_data(lib_project):
    assert "skip_without_data" not in (lib_project / "tests/conftest.py").read_text()


def test_local_notes_are_ignored_from_the_first_commit(gui_project):
    """Ignored as a category, so a scratch file cannot land in a published repo.

    Cheaper to get right at generation time than to purge from history later.
    """
    ignored = (gui_project / ".gitignore").read_text()
    assert "*.local.md" in ignored
