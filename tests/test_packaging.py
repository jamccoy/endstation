"""What the distribution promises, checked against the code.

Packaging metadata is the one part of a project that no other test exercises:
it is read by pip, not by Python, so an extra can be wrong for months while
every test passes. Both failures below were real.
"""

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - 3.10 only
    import tomli as tomllib

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


# -- release -----------------------------------------------------------------


def test_the_release_workflow_uses_no_api_token():
    """Trusted Publishing, not a stored secret.

    A PyPI API token in repository secrets is a credential that can leak, needs
    rotating, and can be printed by any workflow step that is careless with an
    environment dump. OIDC has none of those properties: GitHub attests that
    this workflow produced these artifacts and PyPI accepts that.
    """
    workflow = (PYPROJECT.parent / ".github/workflows/publish.yml").read_text()
    assert "id-token: write" in workflow, "OIDC permission is the mechanism"
    assert "secrets.PYPI" not in workflow, "no API token should be referenced"
    assert "password:" not in workflow


def test_the_release_workflow_checks_the_tag_against_the_version():
    """A version number on PyPI cannot be reused, so a mismatch is permanent.

    Tagging v0.2.0 on a package that still says 0.1.0 publishes the wrong thing
    under a name nobody can take back.
    """
    workflow = (PYPROJECT.parent / ".github/workflows/publish.yml").read_text()
    assert "does not match the built version" in workflow


def test_the_release_workflow_builds_before_it_publishes():
    """Publish the artifact that was checked, not a second build of the source."""
    workflow = (PYPROJECT.parent / ".github/workflows/publish.yml").read_text()
    assert "twine check" in workflow
    assert "upload-artifact" in workflow and "download-artifact" in workflow


def test_every_heredoc_step_declares_bash():
    """A `python - <<'PY'` step must say `shell: bash` or Windows cannot run it.

    PowerShell is the default shell on `windows-latest` and does not understand
    heredoc redirection; the step fails with a parse error that names neither
    the heredoc nor the shell. git-bash is present on GitHub's Windows runners,
    so declaring it costs nothing on the other two platforms.

    Asserted rather than remembered because the failure only appears on the leg
    that is added last, and reads as "Windows is broken" rather than "this step
    was never portable."
    """
    import yaml

    workflow = yaml.safe_load(
        (PYPROJECT.parent / ".github/workflows/test.yml").read_text()
    )
    missing = [
        f"{job}/{step.get('name', '?')}"
        for job, spec in workflow["jobs"].items()
        for step in spec["steps"]
        if "<<'PY'" in str(step.get("run", "")) and step.get("shell") != "bash"
    ]
    assert not missing, f"heredoc steps without `shell: bash`: {missing}"


def test_coverage_is_measured_by_coverage_run_not_pytest_cov():
    """`pytest --cov` under-reports this package by 8 points, and silently.

    pytest imports `pytest11` entry-point plugins before its own conftest --
    which is the entire reason `endstation.testing.plugin` is a plugin. That
    plugin imports `..paths`, which imports the package, which imports the whole
    dependency-free core. Under `--cov` all of it is already imported before
    coverage starts recording, so `forms.py` reports 31% when it is 88% covered.

    A wrong coverage number is worse than none: it is the kind of measurement
    somebody raises a floor against.
    """
    import yaml

    workflow = yaml.safe_load(
        (PYPROJECT.parent / ".github/workflows/test.yml").read_text()
    )
    # The commands only. `--cov` appears in the comments above them, saying
    # exactly this -- and a test that read the raw file would fail on its own
    # explanation.
    commands = [
        str(step.get("run", ""))
        for spec in workflow["jobs"].values()
        for step in spec["steps"]
    ]
    assert any("coverage run -m pytest" in c for c in commands)
    assert not [c for c in commands if "--cov" in c], (
        "pytest --cov misses the imports the pytest11 plugin makes first"
    )
