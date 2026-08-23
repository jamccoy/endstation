"""The toolkit-boundary checker, checked against itself."""

import pytest

from endstation.testing.boundary import (
    TOOLKITS,
    assert_import_free,
    assert_qt_free,
    leaked_imports,
)


def test_a_clean_module_reports_nothing():
    assert leaked_imports("endstation.forms", TOOLKITS) == ()


def test_the_core_is_qt_free():
    assert_qt_free([
        "endstation",
        "endstation.optional",
        "endstation.progress",
        "endstation.forms",
        "endstation.paths",
    ])


def test_a_leak_is_detected():
    """`endstation.qt` is *supposed* to import a toolkit -- so it is the fixture."""
    pytest.importorskip("PySide6", reason="the qt extra is not installed")
    assert "PySide6" in leaked_imports("endstation.qt.jobs", TOOLKITS)


def test_assert_qt_free_fails_on_a_module_that_imports_qt():
    pytest.importorskip("PySide6", reason="the qt extra is not installed")
    with pytest.raises(AssertionError) as excinfo:
        assert_qt_free(["endstation.qt.jobs"])
    assert "PySide6" in str(excinfo.value)


def test_the_failure_says_why_the_boundary_exists():
    pytest.importorskip("PySide6", reason="the qt extra is not installed")
    with pytest.raises(AssertionError) as excinfo:
        assert_qt_free(["endstation.qt.jobs"])
    assert "headlessly" in str(excinfo.value)


def test_an_empty_module_list_is_refused_not_passed():
    """A walk that silently finds nothing must not pass vacuously."""
    with pytest.raises(AssertionError, match="vacuously"):
        assert_qt_free([])


def test_an_unimportable_module_is_a_different_failure():
    """Reporting it as a leak would send a maintainer hunting for an import."""
    with pytest.raises(RuntimeError, match="failed to import"):
        leaked_imports("endstation.no_such_module", TOOLKITS)


def test_the_check_generalises_beyond_qt():
    """Same helper covers "no matplotlib in the CLI"."""
    assert_import_free(["endstation.paths"], ["matplotlib", "numpy"])


# -- discovery --------------------------------------------------------------


def test_discovery_finds_submodules():
    from endstation.testing.boundary import modules_in

    found = modules_in("endstation")
    assert "endstation.forms" in found
    assert "endstation.docs.mathtext" in found


def test_discovery_can_exclude_the_widget_layer():
    """`endstation.qt` is *supposed* to import a toolkit."""
    from endstation.testing.boundary import modules_in

    found = modules_in("endstation", exclude=("endstation.qt",))
    assert not any(m.startswith("endstation.qt") for m in found)


def test_discovery_imports_nothing_it_finds():
    """Safe to call on a package whose submodules need an absent extra."""
    import subprocess
    import sys

    probe = subprocess.run(
        [sys.executable, "-c",
         "import sys\n"
         "from endstation.testing.boundary import modules_in\n"
         "modules_in('endstation')\n"
         "assert 'endstation.docs.mathtext' not in sys.modules, 'discovery imported it'\n"],
        capture_output=True, text=True,
    )
    assert probe.returncode == 0, probe.stderr


def test_discovery_beats_a_hand_written_list():
    """The property this exists for: a new module is covered the day it lands."""
    from endstation.testing.boundary import modules_in

    assert len(modules_in("endstation")) > 10
