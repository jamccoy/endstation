"""Documentation pages: an ordered index, and markdown rendered for a Qt viewer.

Four projects had a version of this and each had a capability the others
lacked -- one rendered LaTeX, one prerendered HTML for an older Qt, one shipped
its pages as package data, one published them to a GitHub wiki. This is the
union.

Toolkit-free: nothing here imports Qt. :mod:`endstation.docs.markdown` produces
HTML plus a dictionary of PNG bytes, and the widget layer registers those with
``QTextDocument.addResource``. That keeps the whole pipeline testable down to
the bytes, with no display.

Needs matplotlib for math rendering, which is the ``mpl`` extra. Structure
conversion alone works without it -- pass ``render_math=False``.
"""

from __future__ import annotations

from .index import Page, PageIndex, load_pages, title_of
from .markdown import MATH_URL_PREFIX, RenderedPage, to_html
from .mathtext import Segment, split_segments, strip_boxed

__all__ = [
    "MATH_URL_PREFIX",
    "Page",
    "PageIndex",
    "RenderedPage",
    "Segment",
    "load_pages",
    "split_segments",
    "strip_boxed",
    "title_of",
    "to_html",
]
