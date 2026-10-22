"""Locating a checkout, and locating data that is deliberately outside it."""

import pytest

from endstation.paths import (
    MissingData,
    data_root,
    find_data,
    find_project_root,
    require_dir,
)


def test_finds_the_marker_walking_up(tmp_path):
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    nested = tmp_path / "src" / "pkg" / "sub"
    nested.mkdir(parents=True)
    assert find_project_root(nested) == tmp_path.resolve()


def test_a_file_resolves_from_its_directory(tmp_path):
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    module = tmp_path / "src" / "mod.py"
    module.parent.mkdir(parents=True)
    module.write_text("", encoding="utf-8")
    assert find_project_root(module) == tmp_path.resolve()


def test_innermost_marker_wins(tmp_path):
    """A nested checkout must not resolve to the outer repository."""
    (tmp_path / ".git").mkdir()
    inner = tmp_path / "vendored"
    inner.mkdir()
    (inner / "pyproject.toml").write_text("", encoding="utf-8")
    assert find_project_root(inner) == inner.resolve()


def test_no_marker_returns_cwd_rather_than_raising(tmp_path, monkeypatch):
    """A wheel has no checkout above it. That is a way to be installed."""
    monkeypatch.chdir(tmp_path)
    assert find_project_root(tmp_path) == tmp_path.resolve()


def test_data_root_prefers_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("TEST_DATA_ROOT", str(tmp_path))
    assert data_root("TEST_DATA_ROOT", "/fallback") == tmp_path


def test_data_root_falls_back_to_the_default(monkeypatch):
    monkeypatch.delenv("TEST_DATA_ROOT", raising=False)
    assert data_root("TEST_DATA_ROOT", "/fallback").as_posix() == "/fallback"


def test_data_root_expands_a_tilde(monkeypatch):
    monkeypatch.delenv("TEST_DATA_ROOT", raising=False)
    assert "~" not in str(data_root("TEST_DATA_ROOT", "~/Documents/ALS"))


def test_data_root_does_not_require_existence(monkeypatch):
    """Asking "where would it be?" must not raise -- skip messages need it."""
    monkeypatch.delenv("TEST_DATA_ROOT", raising=False)
    assert data_root("TEST_DATA_ROOT", "/nowhere/at/all")


def test_empty_env_var_falls_back(monkeypatch):
    """An exported-but-blank variable is not a location."""
    monkeypatch.setenv("TEST_DATA_ROOT", "")
    assert data_root("TEST_DATA_ROOT", "/fallback").as_posix() == "/fallback"


def test_require_dir_returns_an_existing_directory(tmp_path):
    assert require_dir(tmp_path) == tmp_path


def test_missing_dir_names_the_variable_and_the_hint(tmp_path):
    """`FileNotFoundError` on a path the user never typed is unactionable."""
    missing = tmp_path / "absent"
    with pytest.raises(MissingData) as excinfo:
        require_dir(missing, env_var="ALS_DATA_ROOT", hint="docs/DATA.md")
    text = str(excinfo.value)
    assert str(missing) in text
    assert "ALS_DATA_ROOT" in text
    assert "docs/DATA.md" in text


def test_missing_data_is_a_file_not_found_error():
    assert issubclass(MissingData, FileNotFoundError)


def test_find_data_composes_both_steps(monkeypatch, tmp_path):
    monkeypatch.setenv("TEST_DATA_ROOT", str(tmp_path))
    assert find_data("TEST_DATA_ROOT", "/fallback") == tmp_path
