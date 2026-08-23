"""Which documentation pages exist, and what order they read in.

Toolkit-free on purpose, like the rest of the pure layer: a build script needs
to know what to generate, a test needs to check the set is current, and a CLI
``--explain`` should be able to print the same prose the window shows. None of
those should need a GUI installed.

**Ordering is explicit, not alphabetical.** A reader should meet the overview
before the correction it motivates, and alphabetical ordering puts
``facet-fitting`` before ``overview`` for no reason anyone can defend. A page
listed in the order but missing from disk is skipped rather than raising -- a
half-written set should not stop a window opening -- and a page found on disk
but absent from the order is appended, so adding a file does not also require
registering it in a second place.

**A missing directory degrades to an explanatory entry.** Pages that live at
the repository root ship in a checkout and not in a wheel; pages shipped as
package data ship in both. Either is a legitimate arrangement, but a Help menu
that silently loses half its items when installed is not -- so an unavailable
page still appears and says why.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

__all__ = ["Page", "PageIndex", "load_pages"]

_TITLE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class Page:
    """One documentation page, available or not."""

    slug: str
    title: str
    path: Path | None = None
    #: Why this page cannot be shown. Empty when it can.
    unavailable: str = ""

    @property
    def available(self) -> bool:
        return self.path is not None and not self.unavailable

    def read(self) -> str:
        """The markdown source, or the explanation if there is none."""
        if not self.available:
            return f"# {self.title}\n\n{self.unavailable}\n"
        return self.path.read_text(encoding="utf-8")


def title_of(path: Path, fallback: str) -> str:
    """The page's first ``# heading``, or a title made from its filename.

    Reading the title from the content rather than a registry means renaming a
    heading cannot leave a menu entry saying something the page does not.
    """
    try:
        match = _TITLE.search(path.read_text(encoding="utf-8"))
    except OSError:  # pragma: no cover - unreadable file
        return fallback
    return match.group(1).strip() if match else fallback


def _pretty(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").strip().capitalize()


class PageIndex:
    """An ordered collection of :class:`Page`, addressable by slug."""

    def __init__(self, pages: list[Page]) -> None:
        self._pages = list(pages)
        self._by_slug = {p.slug: p for p in self._pages}

    def __iter__(self):
        return iter(self._pages)

    def __len__(self) -> int:
        return len(self._pages)

    def __contains__(self, slug: object) -> bool:
        return slug in self._by_slug

    def __getitem__(self, slug: str) -> Page:
        return self._by_slug[slug]

    @property
    def slugs(self) -> tuple[str, ...]:
        return tuple(p.slug for p in self._pages)

    def available(self) -> tuple[Page, ...]:
        return tuple(p for p in self._pages if p.available)


def load_pages(
    directory: Path | str,
    order: tuple[str, ...] = (),
    *,
    missing_message: str | None = None,
) -> PageIndex:
    """Build an index from ``directory``.

    ``order`` lists slugs -- filenames without ``.md`` -- in reading order.
    Slugs in ``order`` but not on disk are skipped; files on disk but not in
    ``order`` are appended in sorted order.

    If ``directory`` does not exist and ``missing_message`` is given, every slug
    in ``order`` still appears, marked unavailable and carrying that message.
    Without a message, an absent directory yields an empty index.
    """
    directory = Path(directory)

    if not directory.is_dir():
        if missing_message is None:
            return PageIndex([])
        return PageIndex([
            Page(slug=slug, title=_pretty(slug), unavailable=missing_message)
            for slug in order
        ])

    on_disk = {p.stem: p for p in sorted(directory.glob("*.md"))}

    pages: list[Page] = []
    for slug in order:
        path = on_disk.pop(slug, None)
        if path is not None:
            pages.append(Page(slug, title_of(path, _pretty(slug)), path))

    # Whatever the order did not mention, so a new file shows up without also
    # having to be registered.
    for slug, path in on_disk.items():
        pages.append(Page(slug, title_of(path, _pretty(slug)), path))

    return PageIndex(pages)
