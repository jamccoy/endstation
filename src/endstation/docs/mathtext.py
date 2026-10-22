r"""Rendering LaTeX math from a documentation page, without a LaTeX install.

A theory page's ``$$\Phi_m(x) = ...$$`` should not reach a reader as literal
source, backslashes and all. This is the pure half of the fix: splitting a
markdown string into text and math spans, and rasterizing the math spans to PNG
bytes via :func:`matplotlib.mathtext.math_to_image` -- which is already a
dependency wherever there are plots, and needs no live display, so the whole
pipeline down to PNG bytes is headlessly testable. Only the final step of
turning those bytes into an embeddable image needs a real document.

Three things worth knowing before touching this file.

Splitting happens before any escaping. Real documentation contains math
spans holding ``<`` and ``>`` -- ``$t < w$``, ``$\zeta < \theta_c$``,
``$k > 0$``. Escaping first would hand mathtext the string ``t &lt; w``, which
it renders literally. So :func:`split_segments` runs on the raw source and only
the *text* spans are escaped afterwards; the LaTeX never is.

``\boxed{...}`` is not supported by mathtext. It raises ``ValueError``
wrapping a ``ParseFatalException``. :func:`strip_boxed` removes the wrapper by
counting braces rather than by regex, because the boxed content itself contains
nested braces -- ``\boxed{\;G_m = \int_0^1 e^{i\Phi_m(t)}\,dt\;}`` -- and a
naive ``\\boxed\{(.*)\}`` pattern would either stop at the first inner ``}`` or,
greedy, swallow past the intended end. The visual rectangle is not reproduced;
the equation still renders correctly and reads as its own centred line, which is
the part that matters.

A render failure degrades, it does not crash the viewer.
:func:`render_math_png` returns ``None`` rather than propagating the parser's
exception, so one unsupported macro in a future edit shows as visible raw source
for that one span -- diagnosable at a glance -- rather than taking down the
whole page.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "Segment",
    "split_segments",
    "strip_boxed",
    "render_math_png",
]

#: `$$...$$` first so display math is not mistaken for two inline spans.
#: A backslash-escaped `\$` is not a delimiter -- it is a dollar sign, which
#: appears in prose about cost and in any page quoting a shell prompt.
_MATH = re.compile(
    r"(?<!\\)\$\$(?P<display>.+?)(?<!\\)\$\$"
    r"|(?<!\\)\$(?P<inline>[^\n$]+?)(?<!\\)\$",
    re.DOTALL,
)

#: Fenced blocks and inline code, which must be left entirely alone: `$PATH` in
#: a shell example is not the start of an equation.
_CODE = re.compile(r"```.*?```|``.+?``|`[^`\n]+?`", re.DOTALL)


@dataclass(frozen=True)
class Segment:
    """One run of the source: prose, inline math, or display math."""

    text: str
    kind: str = "text"  # "text" | "inline" | "display"

    @property
    def is_math(self) -> bool:
        return self.kind in ("inline", "display")


def split_segments(source: str) -> list[Segment]:
    """Split ``source`` into text and math spans, leaving code untouched.

    Runs on raw markdown, before escaping. See the module docstring.
    """
    segments: list[Segment] = []
    cursor = 0

    # Walk code spans first and only look for math in the gaps between them.
    for code in _CODE.finditer(source):
        _split_prose(source[cursor:code.start()], segments)
        segments.append(Segment(code.group(0), "text"))
        cursor = code.end()
    _split_prose(source[cursor:], segments)

    return [s for s in segments if s.text]


def _split_prose(text: str, out: list[Segment]) -> None:
    """Find math spans in a stretch known to contain no code."""
    cursor = 0
    for match in _MATH.finditer(text):
        if match.start() > cursor:
            out.append(Segment(text[cursor:match.start()], "text"))
        if match.group("display") is not None:
            out.append(Segment(match.group("display").strip(), "display"))
        else:
            out.append(Segment(match.group("inline").strip(), "inline"))
        cursor = match.end()
    if cursor < len(text):
        out.append(Segment(text[cursor:], "text"))


def strip_boxed(latex: str) -> str:
    r"""Remove ``\boxed{...}`` wrappers, counting braces rather than matching.

    mathtext has no boxed macro and raises on one. The content is kept; only
    the wrapper goes. Nested ``\boxed`` is handled by repeating until none is
    left, which costs nothing and avoids a second surprise later.
    """
    marker = r"\boxed{"
    while (start := latex.find(marker)) != -1:
        depth = 0
        for i in range(start + len(marker) - 1, len(latex)):
            if latex[i] == "{":
                depth += 1
            elif latex[i] == "}":
                depth -= 1
                if depth == 0:
                    inner = latex[start + len(marker):i]
                    latex = latex[:start] + inner + latex[i + 1:]
                    break
        else:
            # Unbalanced: drop the marker and keep the rest rather than looping
            # forever on malformed input.
            latex = latex[:start] + latex[start + len(marker):]
    return latex


def render_math_png(
    latex: str,
    *,
    fontsize: int = 12,
    dpi: int = 200,
    color: str = "black",
) -> bytes | None:
    """Rasterize one math span. ``None`` if mathtext cannot parse it.

    Returning ``None`` rather than raising is deliberate: an unsupported macro
    should show as raw source for that one equation, not take down the page.

    ``dpi`` is well above screen resolution because the result is displayed at
    its natural size on a Retina display, where a 100-dpi raster looks soft.
    """
    import io

    from matplotlib import mathtext

    expression = strip_boxed(latex).strip()
    if not expression:
        return None

    buffer = io.BytesIO()
    try:
        mathtext.math_to_image(
            f"${expression}$",
            buffer,
            prop=_font_properties(fontsize),
            dpi=dpi,
            format="png",
            color=color,
        )
    except Exception:  # noqa: BLE001 - any parse failure degrades to raw source
        return None
    return buffer.getvalue()


def _font_properties(fontsize: int):
    from matplotlib.font_manager import FontProperties

    return FontProperties(size=fontsize)
