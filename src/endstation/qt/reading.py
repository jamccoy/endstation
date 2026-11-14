"""A text pane for reading a documentation page, and how to fill one.

:class:`ReadingBrowser` is a ``QTextBrowser`` set up for long prose: a font a
little larger than the widgets around it, a little extra leading, and a text
column held to a readable width and centred, so a wide window adds margin
rather than longer lines. :func:`render_into` converts a markdown page with
:mod:`endstation.docs.markdown`, sized to that font, and registers each
equation's image with the document.

Equations are images in the text colour, and a table's rules and header
shading are the theme's grid and alternate-base colours, both fixed when the
page is set. So a window showing a page should re-render it when the theme
changes (``endstation.qt.theming.subscribe``), not only repaint.
"""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import (
    QFontMetricsF,
    QImage,
    QTextBlockFormat,
    QTextCursor,
    QTextDocument,
    QTextImageFormat,
)
from PySide6.QtWidgets import QTextBrowser, QWidget

from .. import theme as _theme
from ..docs import markdown
from . import theming

__all__ = ["ReadingBrowser", "render_into", "style_sheet", "text_color"]

#: Body text relative to the application font. A page is paragraphs of prose,
#: and the 9 pt that suits a button is small for that.
READING_SCALE = 1.15

#: Widest the text column grows, in ems of the reading font: about 100
#: characters a line. A display equation wider than that widens the column to
#: fit rather than scrolling sideways.
READING_WIDTH_EMS = 50

#: Space either side of the column, in pixels, when the window is narrower
#: than the column.
READING_MARGIN = 24


def style_sheet(theme: _theme.Theme) -> str:
    """The page's default style sheet, in ``theme``'s colours.

    Tables get space around them, which Qt otherwise sets flush against the
    paragraph above, single rules in the grid colour rather than Qt's grey
    double ones, and a header row shaded in the alternate base colour.

    Width and style are spelled out for the cells as well as the table. Qt
    draws a cell border as outset unless told otherwise, which bevels the
    Light theme's grid grey to white and leaves the inner rules invisible,
    and without a width a collapsed rule comes out three pixels thick.
    """
    return (
        "table { margin-top: 6px; margin-bottom: 10px;"
        f" border-collapse: collapse; border-width: 1px; border-style: solid;"
        f" border-color: {theme.grid}; }}"
        f" td, th {{ border-width: 1px; border-style: solid;"
        f" border-color: {theme.grid}; }}"
        f" th {{ text-align: left; background-color: {theme.alt_base}; }}"
    )


#: Extra space between lines, as a fraction of the font's pixel size. A fixed
#: distance rather than CSS ``line-height: 135%``, which scales each line's own
#: height and so opens a wide gap around every line holding an equation.
LEADING = 0.3


class ReadingBrowser(QTextBrowser):
    """A ``QTextBrowser`` laid out for reading a page rather than a log."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        font = self.font()
        font.setPointSizeF(font.pointSizeF() * READING_SCALE)
        self.setFont(font)
        self.document().setDefaultFont(font)
        self._widest_image = 0.0

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt's spelling
        super().resizeEvent(event)
        self._centre_column()

    def pixel_size(self) -> float:
        """The reading font's size in pixels.

        From the point size and the screen's DPI rather than ``QFontInfo``,
        which reports the matched font and so reads near zero where no system
        fonts are installed, as on an offscreen CI run.
        """
        return self.font().pointSizeF() * self.logicalDpiY() / 72.0

    def _centre_column(self) -> None:
        column = max(self.pixel_size() * READING_WIDTH_EMS, self._widest_image)
        spare = self.viewport().width() - column
        side = max(READING_MARGIN, spare / 2)
        root = self.document().rootFrame()
        frame = root.frameFormat()
        if frame.leftMargin() == side and frame.rightMargin() == side:
            return
        frame.setLeftMargin(side)
        frame.setRightMargin(side)
        frame.setTopMargin(READING_MARGIN / 2)
        frame.setBottomMargin(READING_MARGIN)
        root.setFrameFormat(frame)

    def setHtml(self, text: str) -> None:  # noqa: N802 - Qt's spelling
        # The style sheet is read as the HTML is parsed, so the theme in
        # effect now is the one the page is set in.
        self.document().setDefaultStyleSheet(style_sheet(theming.current()))
        # setHtml replaces the root frame's format along with the content.
        super().setHtml(text)
        leading = QTextBlockFormat()
        leading.setLineHeight(
            round(self.pixel_size() * LEADING),
            QTextBlockFormat.LineHeightTypes.LineDistanceHeight.value,
        )
        cursor = QTextCursor(self.document())
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.mergeBlockFormat(leading)
        self._widest_image = _widest_image(self.document())
        self._centre_column()


def _widest_image(document: QTextDocument) -> float:
    """The widest image in a document, in pixels, tables included."""
    widest = 0.0
    block = document.begin()
    while block.isValid():
        fragments = block.begin()
        while not fragments.atEnd():
            fmt = fragments.fragment().charFormat()
            if fmt.isImageFormat():
                widest = max(widest, QTextImageFormat(fmt).width())
            fragments += 1
        block = block.next()
    return widest


def text_color(widget: QWidget) -> str:
    """The widget's palette text colour, for rasterising equations in.

    Equations are images and do not follow a stylesheet, so black math fixed
    at render time would be unreadable on a dark theme.
    """
    return widget.palette().windowText().color().name()


def render_into(
    browser: QTextBrowser,
    source: str,
    *,
    device_pixel_ratio: float,
    text_color: str,
    before: str = "",
) -> markdown.RichPage:
    """Render a markdown page into a browser, images and all.

    Equations are sized to the browser's document font and set on its
    baseline. ``before`` is HTML placed ahead of the page, such as a notice the
    application adds. Returns the rendered page, so a caller can check
    :attr:`~endstation.docs.markdown.RichPage.unrendered`.
    """
    font = browser.document().defaultFont()
    pixels = font.pointSizeF() * browser.logicalDpiY() / 72.0
    rendered = markdown.render_markdown(
        source,
        device_pixel_ratio=device_pixel_ratio,
        color=text_color,
        inline_dpi=markdown.math_dpi(pixels),
        display_dpi=markdown.math_dpi(pixels, display=True),
        **markdown.inline_metrics(pixels, QFontMetricsF(font).xHeight()),
    )
    document = browser.document()
    for image in rendered.images:
        document.addResource(
            QTextDocument.ResourceType.ImageResource,
            QUrl(image.key),
            QImage.fromData(image.png, "PNG"),
        )
    browser.setHtml(before + "\n" + rendered.html if before else rendered.html)
    return rendered
