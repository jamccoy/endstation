r"""LaTeX math from a documentation page, rendered without a LaTeX install.

A page's ``$$\Phi_m(x) = ...$$`` should not reach a reader as literal source.
This module is the pure half: it splits markdown into text and math spans and
rasterizes the math spans to PNG bytes with matplotlib's mathtext, which needs
no display, so everything down to the bytes is testable headlessly. Turning the
bytes into an image a widget shows is :mod:`endstation.docs.markdown`'s job and
the viewer's.

Four points to understand before changing this file.

Splitting runs on the raw source, before anything is escaped. Math spans hold
``<`` and ``>`` (``$t < w$``, ``$k > 0$``), and escaping first would hand
mathtext ``t &lt; w``, which it draws literally.

A ``$`` inside a backtick code span is not a delimiter: ``$PATH`` in a shell
example is not the start of an equation. Fenced blocks never reach this module;
the markdown layer takes them out first.

``\boxed{...}`` is not a mathtext macro and raises. :func:`strip_boxed` removes
the wrapper by counting braces, because the boxed content has braces of its own
(``\boxed{G_m = \int_0^1 e^{i\Phi_m(t)}\,dt}``), so no regex finds the right
closing one. The rectangle is lost; the equation renders.

A render failure returns ``None`` rather than raising, so one unsupported macro
shows as raw source for that span while the rest of the page renders.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__ = ["Segment", "split_segments", "strip_boxed", "render_math_png"]


@dataclass(frozen=True, slots=True)
class Segment:
    """One piece of a page: plain text or a math span.

    ``content`` is the literal markdown for ``"text"``, and the LaTeX without
    its ``$`` or ``$$`` delimiters for ``"math"``. ``display`` is True for
    ``$$...$$``, which sits on its own centred line.
    """

    kind: Literal["text", "math"]
    content: str
    display: bool = False


def split_segments(markdown: str) -> tuple[Segment, ...]:
    r"""Split markdown into alternating text and math segments.

    ``$$...$$`` is display math and ``$...$`` inline. An escaped ``\$`` is a
    literal dollar sign. A backtick code span is copied through untouched, ``$``
    and all. An unterminated ``$`` or ``$$`` is literal text, so a typo shows the
    stray dollar sign instead of raising.
    """
    segments: list[Segment] = []
    buffer: list[str] = []
    i, n = 0, len(markdown)

    def flush_text() -> None:
        if buffer:
            segments.append(Segment(kind="text", content="".join(buffer)))
            buffer.clear()

    while i < n:
        char = markdown[i]

        if char == "\\" and i + 1 < n and markdown[i + 1] == "$":
            buffer.append("$")
            i += 2
            continue

        if char == "`":
            # A code span closes on a run of the same number of backticks. A
            # run with no partner is literal, and parsing carries on after it.
            run = n - len(markdown[i:].lstrip("`"))
            ticks = markdown[i:run]
            close = markdown.find(ticks, run)
            end = run if close == -1 else close + len(ticks)
            buffer.append(markdown[i:end])
            i = end
            continue

        if char == "$":
            display = markdown[i : i + 2] == "$$"
            delimiter = "$$" if display else "$"
            start = i + len(delimiter)
            end = _find_unescaped(markdown, delimiter, start)
            if end == -1:
                buffer.append(markdown[i:])
                i = n
                continue
            flush_text()
            segments.append(
                Segment(kind="math", content=markdown[start:end], display=display)
            )
            i = end + len(delimiter)
            continue

        buffer.append(char)
        i += 1

    flush_text()
    return tuple(segments)


def _find_unescaped(text: str, delimiter: str, start: int) -> int:
    """Index of the next unescaped ``delimiter`` from ``start``, or -1."""
    i = start
    while True:
        i = text.find(delimiter, i)
        if i == -1:
            return -1
        if i > 0 and text[i - 1] == "\\":
            i += len(delimiter)
            continue
        return i


def strip_boxed(latex: str) -> str:
    r"""Remove every ``\boxed{...}`` wrapper, keeping its content.

    Several in one string are handled, as in a side-by-side pair. One with no
    matching close brace is left as it is from that point on.
    """
    marker = "\\boxed{"
    result: list[str] = []
    i, n = 0, len(latex)

    while i < n:
        start = latex.find(marker, i)
        if start == -1:
            result.append(latex[i:])
            break

        result.append(latex[i:start])
        depth = 1
        j = start + len(marker)
        while j < n and depth > 0:
            if latex[j] == "{":
                depth += 1
            elif latex[j] == "}":
                depth -= 1
            j += 1

        if depth != 0:
            result.append(latex[start:])
            break

        result.append(latex[start + len(marker) : j - 1])
        i = j

    return "".join(result)


def render_math_png(
    latex: str,
    *,
    dpi: int = 140,
    color: str = "black",
    axis_pt: float | None = None,
    min_height_pt: float = 0.0,
) -> bytes | None:
    r"""Rasterize a LaTeX string (no ``$`` delimiters) to PNG bytes.

    ``None`` if mathtext cannot parse it. ``\boxed{}`` is stripped first, and
    any run of whitespace becomes one space: a display equation wrapped across
    source lines carries a newline into its LaTeX, which TeX ignores and
    mathtext's parser rejects.

    ``axis_pt`` is for an equation set inside a line of text. Qt places an image
    aligned ``vertical-align: middle`` with its centre a quarter of the font's
    x-height above the baseline, so given that height in points of the 10 pt
    render, space is added above or below until the centre lands there exactly
    when the equation's own baseline sits on the text's. Without it the image's
    bottom edge sits on the baseline, and every symbol with a descender rides
    above the line.

    That rule holds only for an image at least about three x-heights tall; Qt
    sets a shorter one higher, by an amount that depends on its height
    (measured with PySide6 6.11, scanning solid images from 8 to 32 px against a
    14 px font). ``min_height_pt`` pads the image evenly above and below up to
    that height, which keeps the centre where it was.
    """
    import io
    import re

    from matplotlib.mathtext import math_to_image

    normalized = re.sub(r"\s+", " ", strip_boxed(latex)).strip()
    if not normalized:
        return None

    buffer = io.BytesIO()
    try:
        if axis_pt is None:
            math_to_image(f"${normalized}$", buffer, dpi=dpi, format="png", color=color)
            return buffer.getvalue()
        return _inline_png(normalized, dpi, color, axis_pt, min_height_pt)
    except ValueError:
        return None


def _inline_png(
    latex: str, dpi: int, color: str, axis_pt: float, min_height_pt: float
) -> bytes:
    """An inline equation as a transparent PNG, padded about its baseline.

    The baseline is measured, not taken from mathtext's box depth, which is the
    layout box rather than where the glyphs land: at 101 dpi the two differ by a
    pixel either way depending on the expression. So the expression is rendered
    again with an upright ``x`` after it, which sits on the baseline, and the
    bottom of that ``x`` is read off. The two renders share one vertical frame
    whenever the ``x`` is no taller and no deeper than the expression, which is
    any expression holding a letter or digit; otherwise the box depth is used.
    """
    import io

    import numpy as np
    from matplotlib.colors import to_rgb
    from matplotlib.image import imsave
    from matplotlib.mathtext import MathTextParser

    parser = MathTextParser("agg")
    ink = np.asarray(parser.parse(f"${latex}$", dpi=dpi).image)
    probe = parser.parse(f"${latex}" + r"\mathrm{x}$", dpi=dpi)
    probe_ink = np.asarray(probe.image)
    rows = ink.shape[0]
    if probe_ink.shape[0] == rows:
        # The rightmost couple of points of the x: its right leg ends on the
        # baseline, and nothing of the expression reaches that far.
        columns = np.flatnonzero(probe_ink.max(axis=0))
        leg = probe_ink[:, columns[-1] - max(1, round(2 * dpi / 72)) + 1 : columns[-1] + 1]
        baseline = int(np.flatnonzero(leg.max(axis=1) > 100)[-1]) + 1
    else:
        rendered = parser.parse(f"${latex}$", dpi=dpi)
        baseline = int(rendered.height - rendered.depth) - 1

    # Centre on the axis: (above - below) / 2 must equal the axis height.
    scale = dpi / 72.0
    above, below = float(baseline), float(rows - baseline)
    excess = (above - below) - 2 * axis_pt * scale
    if excess > 0:
        below += excess
    else:
        above -= excess
    short = min_height_pt * scale - (above + below)
    if short > 0:
        above += short / 2
        below += short / 2
    top = round(above) - baseline
    bottom = round(below) - (rows - baseline)

    alpha = np.pad(ink, ((top, bottom), (0, 0))).astype(float) / 255.0
    rgba = np.empty(alpha.shape + (4,))
    rgba[..., :3] = to_rgb(color)
    rgba[..., 3] = alpha
    buffer = io.BytesIO()
    imsave(buffer, rgba, format="png")
    return buffer.getvalue()
