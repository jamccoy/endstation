r"""Page indexing, math extraction, and markdown rendered for Qt."""

import pytest

from endstation.docs.index import load_pages, title_of
from endstation.docs.markdown import MATH_URL_PREFIX, UNRENDERED_COLOR, to_html
from endstation.docs.mathtext import split_segments, strip_boxed


# -- the index --------------------------------------------------------------


@pytest.fixture
def docs(tmp_path):
    (tmp_path / "overview.md").write_text("# Overview\n\nStart here.")
    (tmp_path / "icc-correction.md").write_text("# ICC correction\n\nWhy.")
    (tmp_path / "untitled.md").write_text("no heading at all")
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


# -- math extraction --------------------------------------------------------


def test_inline_math_is_split_out():
    kinds = [(s.kind, s.text) for s in split_segments("before $x^2$ after")]
    assert ("inline", "x^2") in kinds


def test_display_math_is_distinguished_from_inline():
    segments = split_segments("$$E = mc^2$$")
    assert [s.kind for s in segments] == ["display"]


def test_a_math_span_containing_an_angle_bracket_survives():
    """Escaping first would hand mathtext `t &lt; w`, rendered literally."""
    segments = split_segments("$t < w$")
    assert segments[0].text == "t < w"


def test_a_dollar_in_a_code_span_is_not_math():
    """`$PATH` in a shell example is not the start of an equation."""
    segments = split_segments("run `echo $PATH` now")
    assert not any(s.is_math for s in segments)


def test_a_dollar_in_a_fenced_block_is_not_math():
    source = "```sh\necho $HOME and $USER\n```"
    assert not any(s.is_math for s in split_segments(source))


def test_an_escaped_dollar_is_not_a_delimiter():
    assert not any(s.is_math for s in split_segments(r"costs \$5 and \$6"))


def test_strip_boxed_counts_braces_rather_than_matching():
    r"""A regex would stop at the first inner `}` or swallow past the end."""
    latex = r"\boxed{\;G_m = \int_0^1 e^{i\Phi_m(t)}\,dt\;}"
    stripped = strip_boxed(latex)
    assert r"\boxed" not in stripped
    assert r"e^{i\Phi_m(t)}" in stripped


def test_strip_boxed_leaves_other_latex_alone():
    assert strip_boxed(r"\frac{a}{b}") == r"\frac{a}{b}"


def test_strip_boxed_survives_an_unbalanced_brace():
    """Malformed input must not loop forever."""
    assert r"\boxed" not in strip_boxed(r"\boxed{unclosed")


# -- rendering --------------------------------------------------------------


def test_structure_converts_without_matplotlib():
    page = to_html("# Title\n\nSome **bold** text.", render_math=False)
    assert "<h1>Title</h1>" in page.html
    assert "<b>bold</b>" in page.html


def test_a_table_becomes_a_table():
    """The tables *are* the content -- an errata list, a reconciliation."""
    source = "| A | B |\n|---|---|\n| 1 | 2 |"
    page = to_html(source, render_math=False)
    assert "<table" in page.html
    assert "<th" in page.html and "<td" in page.html


def test_a_ragged_row_does_not_drop_the_table():
    source = "| A | B |\n|---|---|\n| 1 |"
    page = to_html(source, render_math=False)
    assert "<table" in page.html


def test_lists_convert():
    page = to_html("- one\n- two", render_math=False)
    assert page.html.count("<li>") == 2


def test_numbered_lists_use_ol():
    page = to_html("1. one\n2. two", render_math=False)
    assert "<ol>" in page.html


def test_html_in_the_source_is_escaped():
    """Prose is escaped; only the LaTeX is not."""
    page = to_html("a <script>alert(1)</script> b", render_math=False)
    assert "<script>" not in page.html
    assert "&lt;script&gt;" in page.html


def test_code_spans_do_not_become_bold():
    page = to_html("use `a ** b` here", render_math=False)
    assert "<b>" not in page.html


def test_a_fenced_block_is_preserved_verbatim():
    page = to_html("```\nx = 1 < 2\n```", render_math=False)
    assert "<pre" in page.html
    assert "x = 1 &lt; 2" in page.html


def test_links_survive():
    page = to_html("[units](conventions.md#units)", render_math=False)
    assert '<a href="conventions.md#units">units</a>' in page.html


def test_math_renders_to_an_image_referenced_by_key():
    """QTextDocument.loadResource does not handle data: URLs."""
    pytest.importorskip("matplotlib")
    page = to_html("$$E = mc^2$$")
    assert len(page.images) == 1
    key = next(iter(page.images))
    assert key.startswith(MATH_URL_PREFIX)
    assert f'src="{key}"' in page.html
    assert page.images[key].startswith(b"\x89PNG")


def test_display_math_is_centred_without_nesting_paragraphs():
    pytest.importorskip("matplotlib")
    page = to_html("Before.\n\n$$E = mc^2$$\n\nAfter.")
    assert '<p align="center">' in page.html
    assert "<p><p" not in page.html


def test_an_unrenderable_span_degrades_to_visible_source():
    """One unsupported macro shows as raw source, not a blank page."""
    pytest.importorskip("matplotlib")
    page = to_html(r"text $\nosuchmacro{x}$ more")
    assert page.unrendered == [r"\nosuchmacro{x}"]
    assert page.images == {}
    # The raw source is visible, and marked, so the bad macro is findable.
    assert "nosuchmacro" in page.html
    assert UNRENDERED_COLOR in page.html


def test_render_math_false_skips_rasterising_entirely():
    page = to_html("$$E = mc^2$$", render_math=False)
    assert page.images == {}
    assert page.unrendered == ["E = mc^2"]
