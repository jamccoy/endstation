r"""Splitting math out of markdown, and rasterising it.

matplotlib's Agg rendering needs no display, so this runs headless down to the
PNG bytes.
"""

import pytest

from endstation.docs.mathtext import Segment, render_math_png, split_segments, strip_boxed


class TestSplitSegments:
    def test_plain_text_is_a_single_segment(self):
        assert split_segments("no math here") == (Segment("text", "no math here"),)

    def test_inline_math(self):
        assert split_segments("the value $\\alpha$ is an angle") == (
            Segment("text", "the value "),
            Segment("math", "\\alpha", display=False),
            Segment("text", " is an angle"),
        )

    def test_display_math(self):
        math = [s for s in split_segments("before\n\n$$x = 1$$\n\nafter") if s.kind == "math"]
        assert math == [Segment("math", "x = 1", display=True)]

    def test_adjacent_spans_keep_their_order(self):
        assert [s.content for s in split_segments("$a$ and $b$")] == ["a", " and ", "b"]

    def test_an_escaped_dollar_is_literal(self):
        assert split_segments("costs \\$5 total") == (Segment("text", "costs $5 total"),)

    def test_escaped_dollars_around_real_math(self):
        assert [s.content for s in split_segments("\\$5 then $x$ then \\$10")] == [
            "$5 then ", "x", " then $10"]

    def test_an_unterminated_dollar_is_literal(self):
        assert split_segments("oops $unterminated") == (Segment("text", "oops $unterminated"),)

    def test_unterminated_display_math_is_literal(self):
        assert split_segments("oops $$x") == (Segment("text", "oops $$x"),)

    def test_empty_string(self):
        assert split_segments("") == ()

    def test_display_and_inline_do_not_confuse_each_other(self):
        math = [(s.display) for s in split_segments("a $a$ then $$b$$ done") if s.kind == "math"]
        assert math == [False, True]

    def test_a_math_span_holding_angle_brackets_is_kept_raw(self):
        assert Segment("math", "t < w") in split_segments("valid for $t < w$ only")

    def test_a_dollar_in_a_code_span_is_not_math(self):
        """`$PATH` in a shell example is not the start of an equation."""
        segments = split_segments("set `$PATH` and `$HOME`, then $x$")
        assert [s.content for s in segments if s.kind == "math"] == ["x"]
        assert "`$PATH`" in segments[0].content

    def test_a_double_backtick_span_closes_on_two(self):
        segments = split_segments("``a ` $b$`` then $c$")
        assert [s.content for s in segments if s.kind == "math"] == ["c"]

    def test_a_lone_backtick_does_not_hide_later_math(self):
        segments = split_segments("a stray ` then $x$")
        assert [s.content for s in segments if s.kind == "math"] == ["x"]


class TestStripBoxed:
    def test_no_boxed_is_unchanged(self):
        assert strip_boxed("x = 1") == "x = 1"

    def test_nested_braces(self):
        assert strip_boxed(r"\boxed{G_m = \int_0^1 e^{i\Phi_m(t)}\, dt}") == (
            r"G_m = \int_0^1 e^{i\Phi_m(t)}\, dt")

    def test_two_side_by_side(self):
        stripped = strip_boxed(r"\boxed{\;G = 1\;} \qquad \boxed{\;E = |G|^2\;}")
        assert stripped == r"\;G = 1\; \qquad \;E = |G|^2\;"

    def test_an_unmatched_boxed_is_left_alone(self):
        assert strip_boxed(r"\boxed{unterminated") == r"\boxed{unterminated"

    def test_text_outside_is_kept(self):
        assert strip_boxed(r"before \boxed{x} after") == "before x after"


class TestRenderMathPng:
    @pytest.fixture(autouse=True)
    def _mpl(self):
        pytest.importorskip("matplotlib")

    def test_a_simple_expression_renders(self):
        assert render_math_png(r"\alpha + \beta")[:8] == b"\x89PNG\r\n\x1a\n"

    def test_boxed_renders_via_stripping(self):
        assert render_math_png(r"\boxed{G_m = \int_0^1 e^{i\Phi_m(t)}\,dt}") is not None

    def test_common_macros_render(self):
        for latex in [r"\operatorname{sinc}(x)", r"\text{hello}", r"a \qquad b",
                      r"\Phi_m = k\left[\cos\alpha + \cos\beta_m\right]"]:
            assert render_math_png(latex) is not None, latex

    def test_a_display_equation_wrapped_across_lines_renders(self):
        """mathtext rejects an embedded newline; TeX ignores it."""
        assert render_math_png("a + b\n    = c") is not None

    def test_an_unsupported_macro_returns_none(self):
        assert render_math_png(r"\definitelynotarealmacro{x}") is None

    def test_rendering_is_deterministic(self):
        assert render_math_png(r"\alpha") == render_math_png(r"\alpha")


def _alpha(png):
    import io

    from matplotlib.image import imread

    return imread(io.BytesIO(png), format="png")[..., 3]


def _baseline_below_centre(png):
    """How far the bottom of the leading 'x' sits below the image's centre, in px."""
    alpha = _alpha(png)
    first = alpha[:, : max(2, alpha.shape[1] // 8)]
    bottom = [i for i, row in enumerate(first) if row.max() > 0.4][-1] + 1
    return bottom - alpha.shape[0] / 2


class TestInlinePadding:
    """Inline math is padded so Qt's middle alignment puts it on the baseline."""

    DPI = 101
    AXIS_PT = 1.3
    MIN_PT = 15.6

    @pytest.fixture(autouse=True)
    def _mpl(self):
        pytest.importorskip("matplotlib")

    def render(self, latex):
        return render_math_png(latex, dpi=self.DPI, axis_pt=self.AXIS_PT,
                               min_height_pt=self.MIN_PT)

    def test_the_background_is_transparent(self):
        assert _alpha(self.render("x"))[0, 0] == 0

    def test_the_image_is_at_least_the_minimum_height(self):
        assert _alpha(self.render("x")).shape[0] >= round(self.MIN_PT * self.DPI / 72)

    def test_the_baseline_sits_the_axis_below_the_centre(self):
        axis_px = self.AXIS_PT * self.DPI / 72
        assert _baseline_below_centre(self.render("x")) == pytest.approx(axis_px, abs=1)

    def test_every_expression_puts_its_baseline_in_the_same_place(self):
        """mathtext's box depth is not the glyphs' baseline, and trusting it
        set `x = 0` a pixel or two higher than `x` beside the same text."""
        offsets = {latex: _baseline_below_centre(self.render(latex))
                   for latex in ["x", "x = 0", r"x_{y,m}", r"x = 2\pi/\lambda", r"x \frac{a}{b}"]}
        assert max(offsets.values()) - min(offsets.values()) <= 1, offsets

    def test_an_unsupported_macro_still_returns_none(self):
        assert self.render(r"\definitelynotarealmacro{x}") is None
