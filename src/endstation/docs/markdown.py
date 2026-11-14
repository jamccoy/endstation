r"""Documentation pages as rich text: markdown structure and typeset math.

Qt's rich-text engine reads a small HTML subset, so this module converts a page
to that subset and the viewer only displays it (:mod:`endstation.qt.reading`).
Tables matter as much as equations: real pages keep much of their evidence in
them, and a table left as pipes and dashes is not readable.

Points to understand before editing.

Math is split out before anything is escaped; see
:mod:`endstation.docs.mathtext`. Splitting happens per run of inline text,
after the block structure is known, so an equation inside a table cell is an
equation and a pipe inside an equation is not a column.

Images are referenced by key, not embedded. ``QTextDocument.loadResource`` does
not read ``data:`` URLs, so each equation gets an ``endstation-math:N`` src and
the viewer registers its bytes with ``addResource``.

Equations are sized for the screen. Each is rasterised at the device pixel
ratio and given its logical size in the ``<img>`` tag, so a 2x image is drawn
crisply in a 1x box on a Retina panel. :func:`math_dpi` matches the equations
to the reading font, and :func:`inline_metrics` puts inline ones on the text's
baseline.

A render failure degrades: the raw ``$...$`` appears in
:data:`UNRENDERED_COLOR` and is listed in :attr:`RichPage.unrendered`, so an
unsupported macro is visible and the rest of the page still renders.

Not supported, because no page here uses them and a guessed rendering would be
worse than a visible gap: nested lists, inline HTML, reference-style links and
setext (``===``) headings. A standalone ``---`` is always a rule.

Nothing here imports Qt, and matplotlib is imported only when an equation is
rendered, so structure converts without either.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Callable

from . import mathtext

__all__ = [
    "DISPLAY_DPI",
    "INLINE_DPI",
    "MATH_URL_PREFIX",
    "MathImage",
    "RichPage",
    "UNRENDERED_COLOR",
    "inline_metrics",
    "math_dpi",
    "png_size",
    "render_markdown",
]

#: Rasterisation DPI when the viewer does not pass one from its font
#: (:func:`math_dpi`). Display equations render larger than inline ones, as a
#: printed page sets a headline equation apart from a symbol in running text.
#: Both are scaled by the device pixel ratio.
INLINE_DPI = 130
DISPLAY_DPI = 170

#: The scheme the viewer registers rendered equations under.
MATH_URL_PREFIX = "endstation-math:"

#: Colour for a math span mathtext could not parse: visible, not alarming.
UNRENDERED_COLOR = "#a5370d"

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_RULE_RE = re.compile(r"^(?:-{3,}|_{3,}|\*{3,})$")
_BULLET_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
_NUMBERED_RE = re.compile(r"^\s*\d+[.)]\s+(.*)$")
#: Only a list starting at 1 interrupts a paragraph, as in CommonMark: a
#: wrapped line of prose can begin "120. A real groove".
_INTERRUPTING_NUMBER_RE = re.compile(r"^\s*1[.)]\s+")
#: A cell boundary is a pipe that is not escaped; ``\|`` is a literal pipe,
#: as in an absolute value written in a table.
_CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")
_TABLE_DELIMITER_RE = re.compile(r"^\|[\s:|-]+\|$")
_FENCE_RE = re.compile(r"^```")

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<![\w*])\*([^*\s][^*]*?)\*(?![\w*])")
_CODE_RE = re.compile(r"`([^`]+)`")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_PLACEHOLDER_RE = re.compile(r"\x00(\d+)\x00")


@dataclass(frozen=True, slots=True)
class MathImage:
    """One rasterised equation, to register with a ``QTextDocument``.

    ``width`` and ``height`` are logical pixels: the PNG's own size divided by
    the device pixel ratio it was rendered at.
    """

    key: str
    png: bytes
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class RichPage:
    """A page's HTML, the images its ``<img src>`` keys name, and any
    equations that failed to render, as raw LaTeX (normally none)."""

    html: str
    images: tuple[MathImage, ...] = ()
    unrendered: tuple[str, ...] = ()


@dataclass
class _Collector:
    """Accumulates images while the inline pass walks a page."""

    inline_dpi: int
    display_dpi: int
    device_pixel_ratio: float
    color: str
    render: Callable[..., bytes | None]
    axis_pt: float | None = None
    min_height_pt: float = 0.0
    images: list[MathImage] = field(default_factory=list)
    unrendered: list[str] = field(default_factory=list)

    def add(self, latex: str, *, display: bool) -> str:
        """Render one math span; return the HTML that stands for it."""
        base = self.display_dpi if display else self.inline_dpi
        dpi = max(1, round(base * self.device_pixel_ratio))
        # Only inline math meets a line of text; a display equation has its
        # own line and no baseline to match.
        centred = not display and self.axis_pt is not None
        extra = (
            {"axis_pt": self.axis_pt, "min_height_pt": self.min_height_pt}
            if centred
            else {}
        )
        png = self.render(latex, dpi=dpi, color=self.color, **extra)
        pixels = png_size(png) if png is not None else None

        if pixels is None:
            self.unrendered.append(latex)
            delimiter = "$$" if display else "$"
            source = html.escape(f"{delimiter}{latex}{delimiter}")
            return f'<span style="color:{UNRENDERED_COLOR}">{source}</span>'

        width, height = pixels
        image = MathImage(
            key=f"{MATH_URL_PREFIX}{len(self.images)}",
            png=png,
            width=max(1, round(width / self.device_pixel_ratio)),
            height=max(1, round(height / self.device_pixel_ratio)),
        )
        self.images.append(image)
        align = ' style="vertical-align:middle"' if centred else ""
        tag = (
            f'<img src="{image.key}" width="{image.width}" '
            f'height="{image.height}"{align}>'
        )
        return f"<br>{tag}<br>" if display else tag


def render_markdown(
    markdown: str,
    *,
    inline_dpi: int = INLINE_DPI,
    display_dpi: int = DISPLAY_DPI,
    device_pixel_ratio: float = 1.0,
    color: str = "black",
    render: Callable[..., bytes | None] | None = None,
    render_math: bool = True,
    axis_pt: float | None = None,
    min_height_pt: float = 0.0,
) -> RichPage:
    """Convert markdown with ``$...$`` math to HTML a ``QTextDocument`` shows.

    ``render`` replaces the rasteriser, which lets a test run the pipeline
    without matplotlib, the failure path included. It defaults to a cached
    :func:`~endstation.docs.mathtext.render_math_png`, so reopening a page of
    forty equations is immediate. ``render_math=False`` rasterises nothing and
    shows every equation as source.

    ``color`` is the equations' ink; pass the palette's text colour so they
    stay readable on a dark theme. ``axis_pt`` and ``min_height_pt`` put inline
    math on the text's baseline (see :func:`inline_metrics`); left ``None``, an
    inline equation's bottom edge sits on the baseline instead.
    """
    if not render_math:
        render = _no_render
    collector = _Collector(
        inline_dpi=inline_dpi,
        display_dpi=display_dpi,
        device_pixel_ratio=device_pixel_ratio,
        color=color,
        render=render if render is not None else _cached_render,
        axis_pt=axis_pt,
        min_height_pt=min_height_pt,
    )
    parts = [_block_html(block, collector) for block in _blocks(markdown)]
    return RichPage(
        html="\n".join(p for p in parts if p),
        images=tuple(collector.images),
        unrendered=tuple(collector.unrendered),
    )


def _no_render(latex: str, **_kwargs) -> None:
    return None


# -- block structure -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Block:
    kind: str
    lines: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()
    level: int = 0


def _blocks(markdown: str) -> tuple[_Block, ...]:
    """Split a page into blocks, each recognised by its first line."""
    lines = markdown.split("\n")
    blocks: list[_Block] = []
    i, n = 0, len(lines)

    while i < n:
        line = lines[i]

        if not line.strip():
            i += 1
            continue

        if _FENCE_RE.match(line):
            i += 1
            body: list[str] = []
            while i < n and not _FENCE_RE.match(lines[i]):
                body.append(lines[i])
                i += 1
            i += 1  # the closing fence, or the end of the page
            blocks.append(_Block("code", tuple(body)))
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            blocks.append(
                _Block("heading", (heading.group(2),), level=len(heading.group(1)))
            )
            i += 1
            continue

        if _RULE_RE.match(line.strip()):
            blocks.append(_Block("rule"))
            i += 1
            continue

        if line.lstrip().startswith("|"):
            rows: list[tuple[str, ...]] = []
            while i < n and lines[i].lstrip().startswith("|"):
                if not _TABLE_DELIMITER_RE.match(lines[i].strip()):
                    rows.append(_table_cells(lines[i]))
                i += 1
            blocks.append(_Block("table", rows=tuple(rows)))
            continue

        if line.lstrip().startswith(">"):
            quoted: list[str] = []
            while i < n and lines[i].strip():
                stripped = lines[i].lstrip()
                quoted.append(
                    stripped[1:].strip() if stripped.startswith(">") else stripped
                )
                i += 1
            blocks.append(_Block("quote", (" ".join(quoted),)))
            continue

        for kind, pattern in (("bullets", _BULLET_RE), ("numbered", _NUMBERED_RE)):
            if pattern.match(line):
                items, i = _list_items(lines, i, pattern)
                blocks.append(_Block(kind, items))
                break
        else:
            paragraph: list[str] = []
            while i < n and lines[i].strip() and not _starts_a_block(lines[i]):
                paragraph.append(lines[i].strip())
                i += 1
            blocks.append(_Block("paragraph", (" ".join(paragraph),)))

    return tuple(blocks)


def _list_items(lines: list[str], i: int, pattern: re.Pattern) -> tuple[tuple[str, ...], int]:
    """The items of a list starting at ``lines[i]``, and the index after it.

    A line that does not start an item continues the one above: pages
    soft-wrap at about 80 columns.
    """
    items: list[str] = []
    while i < len(lines) and lines[i].strip():
        match = pattern.match(lines[i])
        if match:
            items.append(match.group(1))
        else:
            items[-1] += " " + lines[i].strip()
        i += 1
    return tuple(items), i


def _starts_a_block(line: str) -> bool:
    """Whether this line begins something other than more paragraph text."""
    stripped = line.lstrip()
    return bool(
        _HEADING_RE.match(line)
        or _RULE_RE.match(line.strip())
        or _FENCE_RE.match(line)
        or stripped.startswith("|")
        or stripped.startswith(">")
        or _BULLET_RE.match(line)
        or _INTERRUPTING_NUMBER_RE.match(line)
    )


def _table_cells(line: str) -> tuple[str, ...]:
    """Cells of one table row, outer pipes discarded, ``\\|`` kept as a pipe."""
    inner = line.strip()
    inner = inner[1:] if inner.startswith("|") else inner
    inner = inner[:-1] if inner.endswith("|") and not inner.endswith("\\|") else inner
    return tuple(cell.strip().replace("\\|", "|") for cell in _CELL_SPLIT_RE.split(inner))


def _block_html(block: _Block, collector: _Collector) -> str:
    if block.kind == "heading":
        return f"<h{block.level}>{_inline(block.lines[0], collector)}</h{block.level}>"

    if block.kind == "paragraph":
        return f"<p>{_inline(block.lines[0], collector)}</p>"

    if block.kind in ("bullets", "numbered"):
        tag = "ul" if block.kind == "bullets" else "ol"
        items = "".join(f"<li>{_inline(item, collector)}</li>" for item in block.lines)
        return f"<{tag}>{items}</{tag}>"

    if block.kind == "quote":
        return f"<blockquote><p>{_inline(block.lines[0], collector)}</p></blockquote>"

    if block.kind == "rule":
        return "<hr>"

    if block.kind == "code":
        # Escaped and left literal: neither markdown nor math is read in code.
        body = html.escape("\n".join(block.lines))
        return f'<pre style="white-space:pre">{body}</pre>'

    if block.kind == "table":
        if not block.rows:
            return ""
        header, *body = block.rows
        width = len(header)
        cells = "".join(f"<th>{_inline(c, collector)}</th>" for c in header)
        out = [f"<tr>{cells}</tr>"]
        for row in body:
            # A short row is padded to the header: a ragged row is a typo, not
            # a reason to lose the table. A long one keeps its extra cells.
            row = row + ("",) * (width - len(row))
            cells = "".join(f"<td>{_inline(c, collector)}</td>" for c in row)
            out.append(f"<tr>{cells}</tr>")
        return (
            '<table border="1" cellpadding="4" cellspacing="0">'
            + "".join(out)
            + "</table>"
        )

    raise AssertionError(f"unhandled block kind {block.kind!r}")  # pragma: no cover


# -- inline structure ----------------------------------------------------


def _inline(raw: str, collector: _Collector) -> str:
    """One run of markdown text, math spans included."""
    out: list[str] = []
    for segment in mathtext.split_segments(raw):
        if segment.kind == "math":
            out.append(collector.add(segment.content, display=segment.display))
        else:
            out.append(_markup(html.escape(segment.content)))
    return "".join(out)


def _markup(escaped: str) -> str:
    """Bold, italic, code and links, applied to already-escaped text.

    Code spans are set aside first, so markup characters in them stay literal,
    and links before emphasis, so a URL is never scanned for asterisks.
    """
    placeholders: list[str] = []

    def stash(fragment: str) -> str:
        placeholders.append(fragment)
        return f"\x00{len(placeholders) - 1}\x00"

    text = _CODE_RE.sub(lambda m: stash(f"<code>{m.group(1)}</code>"), escaped)
    text = _LINK_RE.sub(
        lambda m: stash(f'<a href="{m.group(2)}">{_emphasis(m.group(1))}</a>'), text
    )
    text = _emphasis(text)

    # Repeated, because placeholders nest: a link whose text is a code span
    # holds the code span's placeholder, and re.sub does not rescan what it
    # substituted. It ends because a placeholder only contains lower indices.
    while _PLACEHOLDER_RE.search(text):
        text = _PLACEHOLDER_RE.sub(lambda m: placeholders[int(m.group(1))], text)
    return text


def _emphasis(text: str) -> str:
    text = _BOLD_RE.sub(r"<b>\1</b>", text)
    return _ITALIC_RE.sub(r"<i>\1</i>", text)


# -- sizes ---------------------------------------------------------------


def png_size(data: bytes) -> tuple[int, int] | None:
    """Pixel dimensions from a PNG's IHDR chunk, without a decoder.

    The format fixes the layout: an 8-byte signature, a 4-byte chunk length,
    ``IHDR``, then width and height as big-endian uint32. ``None`` for anything
    that is not a PNG.
    """
    if len(data) < 24 or data[12:16] != b"IHDR":
        return None
    return (
        int.from_bytes(data[16:20], "big"),
        int.from_bytes(data[20:24], "big"),
    )


def inline_metrics(font_pixel_size: float, x_height: float) -> dict[str, float]:
    """``axis_pt`` and ``min_height_pt`` for inline math beside this font.

    Qt puts a middle-aligned image's centre a quarter of the x-height above the
    baseline, if the image is at least three x-heights tall. Both are returned
    in points of the 10 pt math render, in which a pixel of text is
    ``10 / font_pixel_size`` points (see :func:`math_dpi`).
    """
    points = 10.0 / font_pixel_size
    return {"axis_pt": x_height / 4.0 * points, "min_height_pt": 3.0 * x_height * points}


def math_dpi(font_pixel_size: float, *, display: bool = False) -> int:
    """The DPI at which mathtext matches text of this pixel size.

    mathtext renders at ``rcParams["font.size"]``, 10 pt by default, so 72 dpi
    gives ten-pixel glyphs. Scaling by the viewer's font gives equations the
    weight of the prose around them at any zoom or platform default; display
    equations are set 1.3 times larger.
    """
    base = 72.0 * font_pixel_size / 10.0
    return max(1, round(base * (1.3 if display else 1.0)))


@lru_cache(maxsize=512)
def _cached_render(
    latex: str,
    *,
    dpi: int,
    color: str,
    axis_pt: float | None = None,
    min_height_pt: float = 0.0,
) -> bytes | None:
    return mathtext.render_math_png(
        latex, dpi=dpi, color=color, axis_pt=axis_pt, min_height_pt=min_height_pt
    )
