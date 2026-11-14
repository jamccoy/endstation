"""The reading pane: a page rendered into a QTextBrowser."""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtGui import QTextDocument  # noqa: E402

from endstation.qt.reading import ReadingBrowser, render_into, text_color  # noqa: E402

PAGE = "# Title\n\nThe angle $\\alpha$ is small.\n\n$$E = mc^2$$\n\n1. one\n2. two"


@pytest.fixture
def browser(qtbot):
    widget = ReadingBrowser()
    qtbot.addWidget(widget)
    return widget


def test_the_reading_font_is_larger_than_the_widget_default(qtbot):
    from PySide6.QtWidgets import QTextBrowser

    plain = QTextBrowser()
    qtbot.addWidget(plain)
    assert ReadingBrowser().font().pointSizeF() > plain.font().pointSizeF()


def test_every_equation_is_registered_with_the_document(browser):
    pytest.importorskip("matplotlib")
    page = render_into(browser, PAGE, device_pixel_ratio=1.0, text_color="#000000")
    assert len(page.images) == 2 and page.unrendered == ()
    for image in page.images:
        resource = browser.document().resource(
            QTextDocument.ResourceType.ImageResource, QUrl(image.key))
        assert not resource.isNull()


def test_the_page_text_is_shown(browser):
    render_into(browser, PAGE, device_pixel_ratio=1.0, text_color="#000000")
    text = browser.toPlainText()
    assert "Title" in text and "is small." in text and "two" in text


def test_before_is_placed_ahead_of_the_page(browser):
    render_into(browser, "# Title", device_pixel_ratio=1.0, text_color="#000000",
                before="<p>Notice</p>")
    assert browser.toPlainText().startswith("Notice")


def test_a_wide_window_centres_a_column_of_readable_width(browser, qtbot):
    render_into(browser, "words " * 400, device_pixel_ratio=1.0, text_color="#000000")
    browser.resize(3000, 600)
    browser.show()
    qtbot.waitExposed(browser)
    frame = browser.document().rootFrame().frameFormat()
    assert frame.leftMargin() == frame.rightMargin() > 24


def test_text_color_is_the_palette_text_colour(browser):
    assert text_color(browser) == browser.palette().windowText().color().name()


TABLE = "| a | b |\n|---|---|\n| 1 | 2 |\n"


def _table(browser):
    from PySide6.QtGui import QTextCursor

    cursor = QTextCursor(browser.document())
    while not cursor.atEnd():
        found = cursor.currentTable()
        if found is not None:
            return found
        cursor.movePosition(QTextCursor.MoveOperation.NextBlock)
    raise AssertionError("no table in the document")


def test_the_style_sheet_draws_tables_in_the_themes_colours():
    from endstation.qt.reading import style_sheet
    from endstation.theme import DARK

    sheet = style_sheet(DARK)
    assert DARK.grid in sheet and DARK.alt_base in sheet
    assert "border-collapse: collapse" in sheet


def test_a_table_is_set_in_the_theme_current_when_the_page_is(browser, monkeypatch):
    """The rules are one grid-coloured line, not Qt's default bevel, and a
    page set again after a theme change picks up the new colours, which is
    what a window re-rendering on ``theming.subscribe`` relies on."""
    from PySide6.QtGui import QTextFrameFormat

    from endstation.qt import reading
    from endstation.theme import DARK, LIGHT

    for theme in (DARK, LIGHT):
        monkeypatch.setattr(reading.theming, "current", lambda t=theme: t)
        render_into(browser, TABLE, device_pixel_ratio=1.0, text_color=theme.text)
        fmt = _table(browser).format()
        assert fmt.borderBrush().color().name() == theme.grid
        assert fmt.borderStyle() == QTextFrameFormat.BorderStyle.BorderStyle_Solid
        assert fmt.borderCollapse()
