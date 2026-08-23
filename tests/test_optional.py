"""The optional-dependency guards, and the messages they produce.

The messages are the feature. A test that only checked "it raises" would pass
against the bare ``ModuleNotFoundError`` this exists to replace, so every
assertion here is about what the text actually says.
"""

import pytest

from endstation.optional import (
    MissingExtra,
    missing_extra_message,
    optional_module,
    require_extra,
)


def test_present_module_passes_silently():
    require_extra("json", "core")


def test_missing_module_raises_missing_extra():
    with pytest.raises(MissingExtra):
        require_extra("definitely_not_installed_xyz", "gui")


def test_missing_extra_is_a_module_not_found_error():
    """Callers already writing `except ImportError` must keep working."""
    assert issubclass(MissingExtra, ModuleNotFoundError)
    assert issubclass(MissingExtra, ImportError)


def test_message_names_the_module_and_the_extra():
    text = missing_extra_message("PySide6", "gui")
    assert "PySide6" in text
    assert "[gui]" in text


def test_message_quotes_the_install_target():
    """Square brackets are glob characters; zsh refuses them unquoted.

    An unquoted `pip install .[gui]` answers with `no matches found`, which is
    a worse first experience than the ImportError this replaced.
    """
    assert "pip install -e '.[gui]'" in missing_extra_message("PySide6", "gui")
    assert "pip install 'mypkg[gui]'" in missing_extra_message(
        "PySide6", "gui", package="mypkg"
    )


def test_message_can_say_what_still_works():
    text = missing_extra_message(
        "PySide6", "gui", still_works="The analysis works without it."
    )
    assert "The analysis works without it." in text


def test_optional_module_does_not_import_on_construction():
    """The whole point: a missing dependency must not break module import."""
    proxy = optional_module("definitely_not_installed_xyz", "trapezoid")
    assert proxy is not None  # constructing it did not raise


def test_optional_module_raises_on_first_attribute_access():
    proxy = optional_module("definitely_not_installed_xyz", "trapezoid",
                            package="mypkg")
    with pytest.raises(MissingExtra) as excinfo:
        proxy.some_function
    assert "[trapezoid]" in str(excinfo.value)


def test_optional_module_forwards_attributes_when_present():
    proxy = optional_module("json", "core")
    assert proxy.dumps({"a": 1}) == '{"a": 1}'


def test_optional_module_private_attributes_do_not_recurse():
    """`__getattr__` on a private name must raise AttributeError, not recurse."""
    proxy = optional_module("json", "core")
    with pytest.raises(AttributeError):
        proxy._not_a_real_private_attribute


# -- dependencies that are not extras --------------------------------------


def test_an_explicit_install_command_overrides_the_derived_one():
    """Not every optional dependency is one you package.

    PyXFocus's `utilities` comes straight from a git URL; there is no extra to
    name, and the derived `pip install '.[x]'` form cannot express it.
    """
    text = missing_extra_message(
        "utilities.imaging.man",
        install="pip install git+https://github.com/rallured/utilities.git",
    )
    assert "git+https://github.com/rallured/utilities.git" in text
    assert "[" not in text.split("Install it with:")[1]


def test_purpose_says_what_needs_it():
    """"needed for wavefront fitting" tells a reader whether they care."""
    text = missing_extra_message("utilities", purpose="wavefront fitting",
                                 install="pip install utilities")
    assert "needed for wavefront fitting" in text


def test_an_extra_is_still_the_default_shape():
    assert "optional extra" in missing_extra_message("PySide6", "gui")


def test_the_proxy_carries_an_explicit_install_command():
    proxy = optional_module(
        "definitely_not_installed_xyz",
        purpose="testing",
        install="pip install x",
    )
    with pytest.raises(MissingExtra) as excinfo:
        proxy.anything
    assert "pip install x" in str(excinfo.value)
