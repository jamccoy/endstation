"""Copy a project's ``docs/*.md`` into its GitHub wiki checkout.

    endstation-publish-wiki --docs docs --wiki ../myproject.wiki

The repository's ``docs/`` is the source of truth. A GitHub wiki is a separate
git repository, which is why a wiki drifts: two copies are rarely kept in step
by hand, and the copy people read is the one that is not edited.

The formats differ in two ways, and both are handled here.

Wiki links carry no extension. ``[Install](Installation.md)`` resolves in a
repository browser and 404s in a wiki, where it must be
``[Install](Installation)``. The rewrite is confined to links pointing at a page
being published; an external URL or a link to a file that is not a wiki page
is left exactly as written.

Wiki page names are their filenames, with hyphens shown as spaces, so
``Getting-Started.md`` becomes the page "Getting Started". Nothing is renamed
here; the filenames in ``docs/`` are the page names.

This tool never commits and never pushes. It writes files into a checkout and
stops, so that the diff can be read before anything is published. Publishing
docs is outward-facing, and a tool that did it in one step would eventually do
it by accident.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

__all__ = ["publish", "rewrite_links"]

#: A markdown inline link whose target is a local .md file.
_LINK = re.compile(r"(?<!\!)\[([^\]]*)\]\(([^)\s]+?)\.md(#[^)\s]*)?\)")


def rewrite_links(text: str, pages: set[str]) -> str:
    """Drop the ``.md`` from links that point at a page being published.

    ``pages`` is the set of stems that will exist in the wiki. A link to
    something not in it is left alone: it points at a file in the repository
    that the wiki does not have, and silently rewriting it would turn a working
    link into a 404 that looks intentional.
    """

    def replace(match: re.Match[str]) -> str:
        label, target, anchor = match.group(1), match.group(2), match.group(3) or ""
        # Only bare page references. A path like ../src/foo.md is a repository
        # file, not a wiki page.
        if "/" in target or target not in pages:
            return match.group(0)
        return f"[{label}]({target}{anchor})"

    return _LINK.sub(replace, text)


def _read(path: Path) -> str:
    """Read a page as UTF-8, falling back to cp1252 instead of failing.

    The encoding is named because the default is the locale's, which is cp1252
    on Windows, and a UTF-8 page then fails with ``UnicodeDecodeError`` or
    decodes into mojibake. The fallback is for a page saved by an editor that
    still writes the Windows code page: cp1252 decodes every byte but five, so
    it keeps the text where a strict read would stop the whole publish.
    Whatever was read is written back as UTF-8, which is what GitHub expects.

    Line endings are folded to ``\\n`` exactly as a text-mode read folds them,
    so a CRLF checkout of the wiki still compares equal to an LF ``docs/``.
    """
    raw = path.read_bytes()
    try:
        # -sig: a byte order mark is dropped rather than published as text.
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def publish(docs: Path, wiki: Path, *, dry_run: bool = False) -> list[Path]:
    """Copy every ``docs/*.md`` into ``wiki``, rewriting links. Returns what changed."""
    docs, wiki = Path(docs), Path(wiki)
    if not docs.is_dir():
        raise SystemExit(f"docs directory not found: {docs}")
    if not wiki.is_dir():
        raise SystemExit(
            f"wiki checkout not found: {wiki}\n"
            "Clone it alongside the repository:\n"
            "    git clone https://github.com/<user>/<repo>.wiki.git"
        )

    sources = sorted(docs.glob("*.md"))
    if not sources:
        raise SystemExit(f"no .md files in {docs}")

    pages = {p.stem for p in sources}
    changed: list[Path] = []

    for source in sources:
        target = wiki / source.name
        text = rewrite_links(_read(source), pages)
        # Compare before writing so the return value means "differs",
        # which is what makes a dry run worth reading.
        if target.exists() and _read(target) == text:
            continue
        changed.append(target)
        if not dry_run:
            target.write_text(text, encoding="utf-8")

    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs", type=Path, default=Path("docs"))
    parser.add_argument(
        "--wiki", type=Path, required=True,
        help="path to the .wiki checkout, usually a sibling of the repository",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="report what would change without writing",
    )
    args = parser.parse_args(argv)

    changed = publish(args.docs, args.wiki, dry_run=args.dry_run)

    if not changed:
        print("wiki is already up to date")
        return 0

    verb = "would update" if args.dry_run else "updated"
    for path in changed:
        print(f"{verb} {path.name}")
    if not args.dry_run:
        print(f"\nNothing was committed. Review and commit in {args.wiki}:")
        print(f"    git -C {args.wiki} diff")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
