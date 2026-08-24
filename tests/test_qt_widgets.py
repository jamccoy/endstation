"""The canvas pane, the layout floor, and liveness."""

import pytest

pytest.importorskip("PySide6", reason="the qt extra is not installed")

from PySide6.QtWidgets import QPushButton, QScrollArea, QVBoxLayout, QWidget  # noqa: E402

from endstation.qt.canvas import FigurePane, show_message  # noqa: E402
from endstation.qt.liveness import is_alive  # noqa: E402
from endstation.qt.sizing import fit_width_to_contents  # noqa: E402


def test_pane_starts_with_a_placeholder(qtbot):
    pane = FigurePane(placeholder="Load a scan")
    qtbot.addWidget(pane)
    texts = [t.get_text() for ax in pane.figure.axes for t in ax.texts]
    assert "Load a scan" in texts


def test_toolbar_is_optional(qtbot):
    with_bar = FigurePane()
    without = FigurePane(toolbar=False)
    qtbot.addWidget(with_bar)
    qtbot.addWidget(without)
    assert with_bar.toolbar is not None
    assert without.toolbar is None


def test_a_hidden_pane_defers_its_draw(qtbot):
    """A figure in a hidden tab is repainted for nobody."""
    pane = FigurePane()
    qtbot.addWidget(pane)
    pane.clear_axes().plot([0, 1], [0, 1])
    pane.draw()
    assert pane.draw_pending


def test_becoming_visible_flushes_the_pending_draw(qtbot):
    pane = FigurePane()
    qtbot.addWidget(pane)
    pane.draw()
    assert pane.draw_pending
    pane.show()
    qtbot.waitExposed(pane)
    assert not pane.draw_pending


def test_a_visible_pane_draws_immediately(qtbot):
    pane = FigurePane()
    qtbot.addWidget(pane)
    pane.show()
    qtbot.waitExposed(pane)
    pane.draw()
    assert not pane.draw_pending


def test_clear_axes_returns_a_single_fresh_axes(qtbot):
    pane = FigurePane(placeholder="something")
    qtbot.addWidget(pane)
    axes = pane.clear_axes()
    assert pane.figure.axes == [axes]


def test_placeholder_and_refusal_differ_in_colour(qtbot):
    """A refusal is a decision to read, not a state to wait through."""
    pane = FigurePane()
    qtbot.addWidget(pane)

    pane.show_placeholder("nothing yet")
    placeholder = pane.figure.axes[0].texts[0].get_color()

    pane.show_refusal("cannot tile this field")
    refusal = pane.figure.axes[0].texts[0].get_color()

    assert placeholder != refusal


def test_plot_delegates_to_a_toolkit_free_function(qtbot):
    """The drawing lives in a module that knows nothing about Qt."""
    pane = FigurePane()
    qtbot.addWidget(pane)

    def draw(figure):
        figure.add_subplot(111).plot([1, 2, 3], [1, 4, 9])

    pane.plot(draw)
    assert pane.figure.axes[0].lines


def test_show_message_needs_no_widget():
    """So a plotting module with no Qt in it can use it too."""
    from matplotlib.figure import Figure

    figure = Figure()
    show_message(figure, "hello")
    assert figure.axes[0].texts[0].get_text() == "hello"


def test_layout_floor_is_derived_not_hardcoded(qtbot):
    """The number depends on platform button and scrollbar metrics."""
    scroller = QScrollArea()
    qtbot.addWidget(scroller)
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.addWidget(QPushButton("a button wide enough to matter"))
    scroller.setWidget(content)
    scroller.setWidgetResizable(True)

    needed = fit_width_to_contents(scroller)

    assert needed == scroller.minimumWidth()
    assert needed >= content.minimumSizeHint().width()


def test_layout_floor_leaves_room_for_the_scrollbar(qtbot):
    """Declaring a width under the content minimum is a constraint Qt cannot meet.

    It answers with a horizontal scrollbar and a clipped control -- which
    shipped twice unnoticed, because nothing asserted on a pixel.
    """
    scroller = QScrollArea()
    qtbot.addWidget(scroller)
    content = QWidget()
    QVBoxLayout(content).addWidget(QPushButton("button"))
    scroller.setWidget(content)
    scroller.setWidgetResizable(True)

    needed = fit_width_to_contents(scroller)
    bar = scroller.verticalScrollBar().sizeHint().width()
    assert needed >= content.minimumSizeHint().width() + bar


def test_is_alive_on_a_live_widget(qtbot):
    widget = QWidget()
    qtbot.addWidget(widget)
    assert is_alive(widget)


def test_is_alive_of_none_is_false():
    """So one condition covers never-created and already-deleted."""
    assert not is_alive(None)


def test_is_alive_after_qt_deletes_the_c_object(qtbot):
    """What a queued signal arriving during teardown actually hits."""
    import shiboken6

    widget = QWidget()
    shiboken6.delete(widget)
    assert not is_alive(widget)


# -- use_qt_backend ------------------------------------------------------
#
# Monkeypatched rather than driven for real. `matplotlib.use` is process-wide,
# so a test that actually switched the backend would hand every test after it
# a different one -- and the suite runs under Agg on purpose.


def _decide(monkeypatch, backend: str, *, force: bool) -> list[str]:
    """Report which backend `use_qt_backend` would select, selecting none.

    `get_backend` and `use` are patched on the real matplotlib rather than the
    module being replaced wholesale: `require_extra` resolves matplotlib with
    `find_spec`, which consults `sys.modules` and rejects an object with no
    `__spec__`. Patching the two functions leaves the module a real module.
    """
    import matplotlib

    import endstation.qt

    used: list[str] = []
    monkeypatch.setattr(matplotlib, "get_backend", lambda: backend)
    monkeypatch.setattr(matplotlib, "use", used.append)
    endstation.qt.use_qt_backend(force=force)
    return used


def test_a_qt_backend_is_left_alone(monkeypatch):
    """Calling twice is safe; the second call has nothing to do."""
    assert _decide(monkeypatch, "QtAgg", force=False) == []
    assert _decide(monkeypatch, "QtAgg", force=True) == []


def test_agg_is_respected_by_default(monkeypatch):
    """An explicit MPLBACKEND=Agg -- what the headless plugin sets -- wins."""
    assert _decide(monkeypatch, "agg", force=False) == []


def test_force_overrides_agg(monkeypatch):
    """The eblfrac case: a real Qt backend even under test.

    This is the whole reason the keyword exists -- without it that project
    kept a forked copy of this function to get the opposite answer.
    """
    assert _decide(monkeypatch, "agg", force=True) == ["QtAgg"]


def test_a_foreign_backend_is_replaced_either_way(monkeypatch):
    """macOS's default is a second native toolkit in a process already running Qt's."""
    assert _decide(monkeypatch, "macosx", force=False) == ["QtAgg"]
    assert _decide(monkeypatch, "macosx", force=True) == ["QtAgg"]
