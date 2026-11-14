"""Markdown pages as Qt rich text. No Qt and no display: the output is a string
and some PNG bytes."""

import ast
import inspect
import struct
import zlib

import pytest

from endstation.docs import markdown
from endstation.docs.markdown import (
    DISPLAY_DPI,
    INLINE_DPI,
    MATH_URL_PREFIX,
    UNRENDERED_COLOR,
    RichPage,
    inline_metrics,
    math_dpi,
    png_size,
    render_markdown,
)


def fake_render(latex, *, dpi, color, **_):
    """A 4x3 PNG, so rendering runs without matplotlib."""
    def chunk(kind, payload):
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    ihdr = struct.pack(">IIBBBBB", 4, 3, 8, 0, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IEND", b"")


def failing(*_a, **_k):
    return None


def markup(source, **kwargs):
    kwargs.setdefault("render", fake_render)
    return render_markdown(source, **kwargs)


class TestEscaping:
    def test_math_is_split_out_before_anything_is_escaped(self):
        seen = []

        def spy(latex, **kw):
            seen.append(latex)
            return fake_render(latex, **kw)

        markup("Valid for $t < w$ and $k > 0$.", render=spy)
        assert seen == ["t < w", "k > 0"]

    def test_a_bracket_in_prose_cannot_become_a_tag(self):
        html = markup("Compare <script>alert(1)</script> here.").html
        assert "<script>" not in html and "&lt;script&gt;" in html

    def test_an_ampersand_is_escaped(self):
        assert "A &amp; B" in markup("A & B").html

    def test_escaping_does_not_break_bold(self):
        assert "<b>bold</b>" in markup("**bold** & plain").html


class TestInlineMarkup:
    def test_bold_and_italic(self):
        html = markup("**b** and *i* here").html
        assert "<b>b</b>" in html and "<i>i</i>" in html

    def test_code_stays_literal(self):
        assert "<code>a**b**c</code>" in markup("use `a**b**c` now").html

    def test_a_dollar_in_code_is_not_math(self):
        page = markup("run `echo $HOME` then")
        assert page.images == () and "<code>echo $HOME</code>" in page.html

    def test_links_become_anchors(self):
        assert '<a href="conventions.md">the docs</a>' in markup(
            "see [the docs](conventions.md) for more").html

    def test_a_link_url_is_not_scanned_for_emphasis(self):
        assert "a_b_c*d*e.md" in markup("[x](a_b_c*d*e.md)").html

    def test_a_code_span_inside_a_link_survives(self):
        """The code span's placeholder nests inside the link's; one pass of
        re.sub left a raw null byte where the filename should be."""
        html = markup("[`scalar.py`](../src/scalar.py)").html
        assert '<a href="../src/scalar.py"><code>scalar.py</code></a>' in html
        assert "\x00" not in html

    def test_a_lone_asterisk_is_not_emphasis(self):
        assert "<i>" not in markup("2 * 3 = 6").html


class TestBlocks:
    def test_soft_wrapped_paragraphs_are_joined(self):
        html = markup("one two\nthree four\n\nnext").html
        assert "<p>one two three four</p>" in html and html.count("<p>") == 2

    def test_every_heading_level(self):
        html = markup("\n\n".join(f"{'#' * n} h{n}" for n in range(1, 7))).html
        for n in range(1, 7):
            assert f"<h{n}>h{n}</h{n}>" in html

    def test_a_bullet_list_with_a_wrapped_item(self):
        html = markup("- first part\n  second part\n- other").html
        assert "<ul><li>first part second part</li><li>other</li></ul>" in html

    def test_a_numbered_list(self):
        html = markup("1. one\n   more\n2) two").html
        assert "<ol><li>one more</li><li>two</li></ol>" in html

    def test_a_numbered_list_ends_a_paragraph(self):
        html = markup("Steps:\n1. one\n2. two").html
        assert "<p>Steps:</p>" in html and "<ol>" in html

    def test_a_wrapped_line_starting_with_a_number_stays_prose(self):
        """Only a list starting at 1 interrupts a paragraph, as in CommonMark."""
        html = markup("reads 3% shallow at 33 pixels and under 0.5% at\n120. A real groove").html
        assert "<ol>" not in html and "at 120. A real groove</p>" in html

    def test_a_blockquote_joins_its_lines(self):
        assert "<blockquote><p>one two</p></blockquote>" in markup("> one\n> two").html

    def test_a_table(self):
        html = markup("| A | B |\n|---|---|\n| 1 | 2 |").html
        assert html.count("<tr>") == 2 and "<th>A</th>" in html and "---" not in html

    def test_a_ragged_row_is_padded_not_dropped(self):
        html = markup("| A | B |\n|---|---|\n| 1 |").html
        assert "<td>1</td><td></td>" in html

    def test_a_long_row_keeps_its_extra_cells(self):
        assert "<td>3</td>" in markup("| A | B |\n|---|---|\n| 1 | 2 | 3 |").html

    def test_an_escaped_pipe_is_a_pipe_not_a_column(self):
        html = markup("| When | Then |\n|---|---|\n| \\|θ\\| ≥ 0.2° | yes |").html
        assert "<td>|θ| ≥ 0.2°</td><td>yes</td>" in html

    def test_math_in_a_table_cell_is_an_image(self):
        page = markup("| $a$ | b |\n|---|---|\n| 1 | 2 |")
        assert "<th><img " in page.html and len(page.images) == 1

    def test_a_rule_is_not_a_heading_underline(self):
        assert markup("text\n\n---\n\nmore").html.count("<hr>") == 1

    def test_a_fenced_block_stays_literal(self):
        html = markup("```\na = **b** < $c$\n```").html
        assert "<pre" in html and "**b** &lt; $c$" in html and "<b>" not in html

    def test_an_unclosed_fence_is_still_code(self):
        assert "<pre" in markup("```\nx = 1").html

    def test_an_empty_page(self):
        assert markup("").html == ""

    def test_blank_lines_make_no_empty_paragraphs(self):
        assert "<p></p>" not in markup("a\n\n\n\nb").html


class TestImages:
    def test_each_equation_is_an_image_referenced_by_key(self):
        """QTextDocument.loadResource does not read data: URLs."""
        page = markup("$a$ and $$b$$")
        keys = [image.key for image in page.images]
        assert keys == [f"{MATH_URL_PREFIX}0", f"{MATH_URL_PREFIX}1"]
        for key in keys:
            assert f'src="{key}"' in page.html

    def test_display_math_gets_its_own_line(self):
        assert "<br><img " in markup("before\n\n$$b$$\n\nafter").html

    def test_display_equations_render_larger_than_inline_ones(self):
        seen = {}

        def spy(latex, **kw):
            seen[latex] = kw["dpi"]
            return fake_render(latex, **kw)

        markup("inline $a$\n\n$$b$$", render=spy)
        assert (seen["a"], seen["b"]) == (INLINE_DPI, DISPLAY_DPI)

    def test_a_retina_ratio_rasterises_at_double_resolution_shown_at_logical_size(self):
        seen = []

        def spy(latex, **kw):
            seen.append(kw["dpi"])
            return fake_render(latex, **kw)

        two = markup("$a$", device_pixel_ratio=2.0, render=spy).images[0]
        assert seen == [2 * INLINE_DPI]
        assert (two.width, two.height) == (2, 2)  # a 4x3 PNG at 2x

    def test_a_logical_size_never_rounds_to_zero(self):
        assert markup("$a$", device_pixel_ratio=8.0).images[0].width >= 1

    def test_the_colour_reaches_the_renderer(self):
        seen = []
        markup("$a$", color="#eeeeee",
               render=lambda latex, **kw: seen.append(kw["color"]) or fake_render(latex, **kw))
        assert seen == ["#eeeeee"]


class TestInlineAlignment:
    def test_inline_math_is_middle_aligned_and_given_the_metrics(self):
        calls = []

        def spy(latex, **kw):
            calls.append(kw)
            return fake_render(latex, **kw)

        html = render_markdown("a $x$ b\n\n$$y$$", render=spy, axis_pt=1.5,
                               min_height_pt=15.0).html
        inline, display = calls
        assert inline["axis_pt"] == 1.5 and inline["min_height_pt"] == 15.0
        assert "axis_pt" not in display
        assert html.count("vertical-align:middle") == 1

    def test_without_an_axis_nothing_is_aligned(self):
        assert "vertical-align" not in markup("a $x$ b").html

    def test_metrics_are_in_points_of_the_ten_point_render(self):
        assert inline_metrics(20.0, 10.0) == {"axis_pt": 1.25, "min_height_pt": 15.0}


class TestDegradation:
    def test_an_unparseable_span_shows_its_source_in_colour(self):
        page = render_markdown("before $\\notamacro{x}$ after", render=failing)
        assert UNRENDERED_COLOR in page.html and "\\notamacro{x}" in page.html
        assert page.unrendered == ("\\notamacro{x}",) and page.images == ()

    def test_the_rest_of_the_page_survives(self):
        html = render_markdown("## H\n\ntext $bad$\n\n| a |\n|---|\n| b |", render=failing).html
        assert "<h2>H</h2>" in html and "<table" in html

    def test_the_failed_source_is_escaped(self):
        assert "&lt;" in render_markdown("$a < b$", render=failing).html

    def test_render_math_false_rasterises_nothing(self):
        page = render_markdown("# T\n\n$$E = mc^2$$", render_math=False)
        assert "<h1>T</h1>" in page.html
        assert page.images == () and page.unrendered == ("E = mc^2",)

    def test_the_real_renderer_draws_an_equation(self):
        pytest.importorskip("matplotlib")
        page = render_markdown("$$E = mc^2$$")
        assert page.unrendered == () and page.images[0].png.startswith(b"\x89PNG")


class TestSizes:
    def test_png_size_reads_the_header(self):
        assert png_size(fake_render("x", dpi=1, color="k")) == (4, 3)

    def test_png_size_refuses_what_is_not_a_png(self):
        assert png_size(b"\x89PNG") is None and png_size(b"x" * 64) is None

    def test_ten_point_text_wants_seventy_two_dpi(self):
        assert math_dpi(10.0) == 72 and math_dpi(20.0) == 144

    def test_display_equations_get_a_boost(self):
        assert math_dpi(10.0, display=True) > math_dpi(10.0)

    def test_math_dpi_is_never_zero(self):
        assert math_dpi(0.0) >= 1


class TestPurity:
    def test_imports_no_toolkit(self):
        imported = set()
        for node in ast.walk(ast.parse(inspect.getsource(markdown))):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert not {"tkinter", "PySide6", "PyQt6", "PyQt5"} & imported

    def test_returns_a_richpage(self):
        assert isinstance(markup("x"), RichPage)

    def test_the_same_equation_is_rasterised_once(self):
        pytest.importorskip("matplotlib")
        markdown._cached_render.cache_clear()
        render_markdown("$x$ and $x$ and $y$")
        info = markdown._cached_render.cache_info()
        assert (info.misses, info.hits) == (2, 1)
