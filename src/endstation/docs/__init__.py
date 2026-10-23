"""Documentation pages: an ordered index, and markdown rendered for a Qt viewer.

Four projects had a version of this, and each had a capability the others
lacked: one rendered LaTeX, one prerendered HTML for an older Qt, one shipped
its pages as package data, and one published them to a GitHub wiki. This
subpackage combines all four.

The subpackage is toolkit-free, and nothing here imports Qt.
:mod:`endstation.docs.markdown` produces HTML plus a dictionary of PNG bytes,
and the widget layer registers those with ``QTextDocument.addResource``. As a
result the whole pipeline can be tested down to the bytes without a display.

Math rendering needs matplotlib, which is the ``mpl`` extra. Structure
conversion alone works without it if ``render_math=False`` is passed.
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
