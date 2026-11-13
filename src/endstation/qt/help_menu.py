"""A Help menu: an About box first, then groups of pages, built the same in every window.

:func:`install_help_menu` adds the menu to a window's bar (or to a bar the
caller passes, for a plain ``QWidget`` that keeps its own) and returns it. The
caller supplies the About title and a function returning its text, and the
pages as groups of ``(label, open)`` pairs, each group set off by a separator.
What a page is and how it opens stays in the application.

The menu is also stored on the window as ``_endstation_help_menu``. Under
PySide6 a QMenu reached back through ``menuBar().actions()[i].menu()`` is not
reliably usable, so whatever builds a menu must keep a reference to it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence

from PySide6.QtWidgets import QMessageBox

__all__ = ["HELP_MENU_TITLE", "install_help_menu", "show_about"]

#: Title of the menu, one constant so a test and every window agree.
HELP_MENU_TITLE = "&Help"


def show_about(parent, title: str, text: str) -> None:
    """The About box: ``title`` in the title bar and ``text`` as its body."""
    QMessageBox.about(parent, title, text)


def install_help_menu(
    window,
    *,
    about_title: str,
    about_text: Callable[[], str],
    pages: Iterable[Sequence[tuple[str, Callable[[], object]]]] = (),
    menu_bar=None,
):
    """Add the Help menu to ``window`` and return it.

    ``about_title`` is the About action's label and the box's title, for
    example ``"About gratinglab"``. ``about_text`` is called when the box
    opens, so a version read at that moment is current. ``pages`` is a
    sequence of groups; each group is a sequence of ``(label, open)`` pairs,
    where ``open`` takes no arguments.
    """
    bar = window.menuBar() if menu_bar is None else menu_bar
    menu = bar.addMenu(HELP_MENU_TITLE)
    menu.addAction(about_title, lambda: show_about(window, about_title, about_text()))
    for group in pages:
        group = list(group)
        if not group:
            continue
        menu.addSeparator()
        for label, opener in group:
            menu.addAction(label, opener)
    window._endstation_help_menu = menu
    return menu
