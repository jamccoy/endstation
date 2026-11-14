"""Page indexing. Rendering is tested in test_docs_mathtext.py and test_docs_markdown.py."""

import pytest

from endstation.docs.index import load_pages, title_of


# -- the index --------------------------------------------------------------


@pytest.fixture
def docs(tmp_path):
    (tmp_path / "overview.md").write_text("# Overview\n\nStart here.", encoding="utf-8")
    (tmp_path / "icc-correction.md").write_text("# ICC correction\n\nWhy.", encoding="utf-8")
    (tmp_path / "untitled.md").write_text("no heading at all", encoding="utf-8")
    return tmp_path


def test_explicit_order_beats_alphabetical(docs):
    """A reader meets the overview before the correction it motivates."""
    index = load_pages(docs, order=("overview", "icc-correction"))
    assert index.slugs[:2] == ("overview", "icc-correction")


def test_a_page_missing_from_disk_is_skipped_not_raised(docs):
    """A half-written set must not stop a window opening."""
    index = load_pages(docs, order=("overview", "not-written-yet"))
    assert "not-written-yet" not in index


def test_a_page_not_in_the_order_is_still_included(docs):
    """So adding a file does not also mean registering it in a second place."""
    index = load_pages(docs, order=("overview",))
    assert "untitled" in index


def test_title_comes_from_the_heading(docs):
    index = load_pages(docs, order=("overview",))
    assert index["overview"].title == "Overview"


def test_a_page_with_no_heading_falls_back_to_its_filename(docs):
    index = load_pages(docs, order=())
    assert index["untitled"].title == "Untitled"


def test_title_of_uses_the_fallback_for_a_missing_file(tmp_path):
    assert title_of(tmp_path / "absent.md", "Fallback") == "Fallback"


def test_a_missing_directory_yields_an_empty_index():
    assert len(load_pages("/nowhere/at/all", order=("a",))) == 0


def test_a_missing_directory_can_still_list_its_pages():
    """A Help menu that silently loses half its items when installed is worse."""
    index = load_pages("/nowhere", order=("a", "b"),
                       missing_message="Only present in a checkout.")
    assert index.slugs == ("a", "b")
    assert not index["a"].available
    assert "Only present in a checkout." in index["a"].read()


def test_available_filters_the_unreadable(docs):
    index = load_pages(docs, order=("overview",))
    assert all(p.available for p in index.available())
