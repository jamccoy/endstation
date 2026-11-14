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
