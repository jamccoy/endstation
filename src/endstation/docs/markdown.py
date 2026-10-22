r"""Documentation pages as rich text: markdown structure *and* typeset math.

Qt's rich-text engine parses a small HTML subset, which makes this cheap: this
module converts a page to that subset, and the widget layer only displays it.

Getting equations rendering and stopping there is a tempting place to stop, and
it goes bad: tables and bullet lists stay as literal pipes and dashes. Real
documentation puts the evidence *in* the tables -- an angle-convention
reconciliation, an errata list, a three-way comparison -- and those are the
content, in the one place a reader goes to understand what the software does.

No markdown dependency. The subset Qt renders is small enough that a full
CommonMark implementation would mostly be output this cannot use, and the
conversion has to interleave with math extraction anyway (see below). This
handles headings, paragraphs, bullet and numbered lists, tables, fenced and
inline code, bold, italic, links, block quotes and rules, which is what the
pages contain.

Three things worth knowing before editing:

Math is split out before anything is escaped. Math spans in real pages
contain ``<`` and ``>``. Escaping first would hand mathtext ``t &lt; w``, which
it renders literally. So :func:`~endstation.docs.mathtext.split_segments` runs
on the raw source and only the *text* spans are escaped.

Images are referenced by key, not embedded. ``QTextDocument.loadResource``
does not handle ``data:`` URLs, so each rendered equation gets an
``endstation-math:N`` src and the viewer registers the bytes with
``addResource``. That also keeps this module free of base64 padding it would
only have to undo.

A render failure degrades rather than crashing. The raw ``$...$`` source
appears in a distinct colour, so a future edit using an unsupported macro is
diagnosable at a glance instead of taking down the page.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

from .mathtext import render_math_png, split_segments

__all__ = ["MATH_URL_PREFIX", "RenderedPage", "UNRENDERED_COLOR", "to_html"]

#: Scheme the viewer registers rendered equations under. Not `data:`.
MATH_URL_PREFIX = "endstation-math:"

#: Colour for a math span mathtext could not parse. Visible, not alarming.
UNRENDERED_COLOR = "#b3541e"


@dataclass
class RenderedPage:
    """HTML for a ``QTextDocument``, plus the images it refers to."""

    html: str
    images: dict[str, bytes] = field(default_factory=dict)
    #: Math spans that failed to render, as raw LaTeX. Empty is the normal case.
    unrendered: list[str] = field(default_factory=list)


# -- inline formatting ------------------------------------------------------

_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<![*\w])\*([^*\n]+)\*(?!\*)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def _inline(text: str) -> str:
    """Escape, then apply inline markup. Order matters: escaping is first."""
    out = html.escape(text)
    # Code first, so `**` inside a code span is not turned into bold.
    out = _INLINE_CODE.sub(
        lambda m: f'<code style="background-color:#f0f0f0;">{m.group(1)}</code>',
        out,
    )
    out = _BOLD.sub(r"<b>\1</b>", out)
    out = _ITALIC.sub(r"<i>\1</i>", out)
    out = _LINK.sub(r'<a href="\2">\1</a>', out)
    return out


# -- block structure --------------------------------------------------------

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^\s*[-*+]\s+(.*)$")
_NUMBERED = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_RULE = re.compile(r"^\s*([-*_])\s*(\1\s*){2,}$")
_QUOTE = re.compile(r"^>\s?(.*)$")
_TABLE_DIVIDER = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def _split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _blocks_to_html(lines: list[str]) -> str:
    """Convert already-math-substituted lines into Qt's HTML subset."""
    out: list[str] = []
    index = 0
    total = len(lines)

    while index < total:
        line = lines[index]

        if not line.strip():
            index += 1
            continue

        # Fenced code
        if line.lstrip().startswith("```"):
            body: list[str] = []
            index += 1
            while index < total and not lines[index].lstrip().startswith("```"):
                body.append(html.escape(lines[index]))
                index += 1
            index += 1  # closing fence
            out.append(
                '<pre style="background-color:#f0f0f0;">'
                + "\n".join(body)
                + "</pre>"
            )
            continue

        if _RULE.match(line):
            out.append("<hr />")
            index += 1
            continue

        heading = _HEADING.match(line)
        if heading:
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            index += 1
            continue

        # Table: a header row followed by a divider row.
        if (
            "|" in line
            and index + 1 < total
            and _TABLE_DIVIDER.match(lines[index + 1])
        ):
            header = _split_row(line)
            index += 2
            rows = []
            while index < total and "|" in lines[index] and lines[index].strip():
                rows.append(_split_row(lines[index]))
                index += 1
            out.append(_table_html(header, rows))
            continue

        if _QUOTE.match(line):
            body = []
            while index < total and _QUOTE.match(lines[index]):
                body.append(_QUOTE.match(lines[index]).group(1))
                index += 1
            out.append(
                '<blockquote style="color:#555;">'
                f"{_inline(' '.join(body))}</blockquote>"
            )
            continue

        if _BULLET.match(line) or _NUMBERED.match(line):
            numbered = bool(_NUMBERED.match(line))
            tag = "ol" if numbered else "ul"
            items = []
            while index < total:
                match = (_NUMBERED if numbered else _BULLET).match(lines[index])
                if not match:
                    break
                items.append(f"<li>{_inline(match.group(1))}</li>")
                index += 1
            out.append(f"<{tag}>{''.join(items)}</{tag}>")
            continue

        # Paragraph: consecutive non-blank lines that start nothing else.
        body = []
        while index < total and lines[index].strip():
            candidate = lines[index]
            if (
                _HEADING.match(candidate)
                or _BULLET.match(candidate)
                or _NUMBERED.match(candidate)
                or _RULE.match(candidate)
                or _QUOTE.match(candidate)
                or candidate.lstrip().startswith("```")
            ):
                break
            body.append(candidate)
            index += 1
        if body:
            out.append(f"<p>{_inline(' '.join(body))}</p>")

    return "\n".join(out)


def _table_html(header: list[str], rows: list[list[str]]) -> str:
    """A bordered table. Qt honours the `border` attribute, not CSS borders."""
    head = "".join(
        f'<th style="padding:4px 8px;background-color:#ececec;">{_inline(c)}</th>'
        for c in header
    )
    body = []
    for row in rows:
        # Pad or trim to the header width; a ragged row is a typo, not a reason
        # to drop the table.
        cells = (row + [""] * len(header))[: len(header)]
        body.append(
            "<tr>"
            + "".join(
                f'<td style="padding:4px 8px;">{_inline(c)}</td>' for c in cells
            )
            + "</tr>"
        )
    return (
        '<table border="1" cellspacing="0" cellpadding="0" '
        'style="margin:8px 0;">'
        f"<tr>{head}</tr>{''.join(body)}</table>"
    )


# -- the public entry point -------------------------------------------------

#: A paragraph containing nothing but a centred paragraph. See `to_html`.
_UNWRAP_NESTED_P = re.compile(r"<p>\s*(<p align=\"center\">.*?</p>)\s*</p>",
                              re.DOTALL)

#: Placeholder inserted where a math span was, before block parsing runs, so an
#: equation cannot be mistaken for a table pipe or a list bullet.
_TOKEN = "\x00MATH{}\x00"


def to_html(source: str, *, render_math: bool = True) -> RenderedPage:
    """Convert a markdown page to the HTML subset ``QTextDocument`` renders.

    ``render_math=False`` skips rasterisation entirely -- for a test that cares
    about structure, or an environment with no matplotlib.
    """
    segments = split_segments(source)

    images: dict[str, bytes] = {}
    unrendered: list[str] = []
    replacements: dict[str, str] = {}
    text_parts: list[str] = []

    for i, segment in enumerate(segments):
        if not segment.is_math:
            text_parts.append(segment.text)
            continue

        token = _TOKEN.format(i)
        png = render_math_png(segment.text) if render_math else None

        if png is None:
            unrendered.append(segment.text)
            raw = html.escape(f"${segment.text}$")
            replacements[token] = (
                f'<span style="color:{UNRENDERED_COLOR};">{raw}</span>'
            )
        else:
            key = f"{MATH_URL_PREFIX}{len(images)}"
            images[key] = png
            tag = f'<img src="{key}" />'
            # Display math gets its own centred line; inline sits in the run.
            replacements[token] = (
                f'<p align="center">{tag}</p>' if segment.kind == "display" else tag
            )

        text_parts.append(token)

    html_body = _blocks_to_html("".join(text_parts).splitlines())

    # Substituted after block parsing, so the `<img>` markup cannot be escaped
    # by `_inline` on its way through.
    for token, markup in replacements.items():
        html_body = html_body.replace(html.escape(token), markup)
        html_body = html_body.replace(token, markup)

    # A display equation on its own line arrives here as a paragraph whose only
    # content is a centred paragraph. Qt tolerates the nesting but lays it out
    # with the outer paragraph's spacing *and* the inner one's, which reads as
    # an accidental gap; unwrapping keeps display math spaced like every other
    # block.
    html_body = _UNWRAP_NESTED_P.sub(r"\1", html_body)

    return RenderedPage(html=html_body, images=images, unrendered=unrendered)
