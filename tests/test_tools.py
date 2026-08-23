"""Bundle building, bundle checking, and wiki publishing."""

import plistlib
import sys

import pytest

from endstation.tools.make_app import App, build_app, check_app
from endstation.tools.make_icon import VARIANTS
from endstation.tools.publish_wiki import publish, rewrite_links

darwin_only = pytest.mark.skipif(
    sys.platform != "darwin", reason=".app bundles are macOS-only"
)


@pytest.fixture
def launcher(tmp_path):
    script = tmp_path / "demo-gui"
    script.write_text("#!/bin/sh\necho ran\n")
    script.chmod(0o755)
    return script


@pytest.fixture
def app(launcher):
    return App(name="Demo App", launcher=launcher, bundle_id="org.example.demo",
               version="1.2.3")


# -- the icon variants ------------------------------------------------------


def test_every_macos_iconset_name_is_present():
    """iconutil is fussy: a wrong name fails without saying which."""
    names = {name for _, name in VARIANTS}
    assert len(VARIANTS) == 10
    for base in (16, 32, 128, 256, 512):
        assert f"icon_{base}x{base}.png" in names
        assert f"icon_{base}x{base}@2x.png" in names


def test_retina_variants_are_twice_their_base():
    sizes = dict((name, px) for px, name in VARIANTS)
    for base in (16, 32, 128, 256, 512):
        assert sizes[f"icon_{base}x{base}@2x.png"] == 2 * sizes[f"icon_{base}x{base}.png"]


# -- bundle identity --------------------------------------------------------


def test_stem_strips_spaces_from_the_name(app):
    """It names a file inside the bundle, where a space is a nuisance."""
    assert app.stem == "DemoApp"


def test_an_explicit_stem_is_kept(launcher):
    app = App(name="Demo App", launcher=launcher, bundle_id="x", stem="Custom")
    assert app.stem == "Custom"


def test_min_macos_defaults_to_the_pyside_floor(app):
    """PySide6-Essentials ships macosx_13_0; claiming less lets Finder launch
    a bundle whose window can never open."""
    assert app.min_macos == "13.0"


# -- building ---------------------------------------------------------------


@darwin_only
def test_builds_a_well_formed_bundle(app, tmp_path):
    bundle = build_app(app, tmp_path)
    assert bundle.name == "DemoApp.app"
    assert (bundle / "Contents" / "Info.plist").is_file()
    assert (bundle / "Contents" / "MacOS" / "DemoApp").is_file()


@darwin_only
def test_the_stub_is_executable(app, tmp_path):
    import os

    bundle = build_app(app, tmp_path)
    assert os.access(bundle / "Contents" / "MacOS" / "DemoApp", os.X_OK)


@darwin_only
def test_plist_carries_the_identity(app, tmp_path):
    bundle = build_app(app, tmp_path)
    info = plistlib.loads((bundle / "Contents" / "Info.plist").read_bytes())
    assert info["CFBundleName"] == "Demo App"
    assert info["CFBundleIdentifier"] == "org.example.demo"
    assert info["CFBundleShortVersionString"] == "1.2.3"
    assert info["NSHighResolutionCapable"] is True


@darwin_only
def test_the_logging_stub_names_a_log_and_can_alert(app, tmp_path):
    """A .app that fails silently is useless: an icon bounces once, no clue why."""
    bundle = build_app(app, tmp_path, stub="logging")
    stub = (bundle / "Contents" / "MacOS" / "DemoApp").read_text()
    assert "Library/Logs/DemoApp.log" in stub
    assert "osascript" in stub


@darwin_only
def test_the_thin_stub_is_just_an_exec(app, tmp_path):
    bundle = build_app(app, tmp_path, stub="thin")
    stub = (bundle / "Contents" / "MacOS" / "DemoApp").read_text()
    assert "exec " in stub
    assert "osascript" not in stub


@darwin_only
def test_rebuilding_replaces_rather_than_merges(app, tmp_path):
    bundle = build_app(app, tmp_path)
    stale = bundle / "Contents" / "Resources" / "leftover.txt"
    stale.write_text("from a previous build")
    build_app(app, tmp_path)
    assert not stale.exists()


@darwin_only
def test_a_missing_launcher_is_refused_with_an_install_hint(tmp_path):
    app = App(name="Demo", launcher=tmp_path / "nope", bundle_id="x")
    with pytest.raises(SystemExit, match="pip install"):
        build_app(app, tmp_path)


@darwin_only
def test_a_missing_icon_points_at_the_icon_tool(launcher, tmp_path):
    app = App(name="Demo", launcher=launcher, bundle_id="x",
              icon=tmp_path / "absent.icns")
    with pytest.raises(SystemExit, match="endstation-icon"):
        build_app(app, tmp_path)


# -- checking ---------------------------------------------------------------


@darwin_only
def test_a_fresh_bundle_checks_clean(app, tmp_path):
    assert check_app(build_app(app, tmp_path)) == []


@darwin_only
def test_check_catches_a_launcher_that_moved(app, tmp_path, launcher):
    """The usual breakage: the repository moved, the icon bounces once."""
    bundle = build_app(app, tmp_path)
    launcher.unlink()
    problems = check_app(bundle)
    assert any("launcher no longer exists" in p for p in problems)


def test_check_reports_a_bundle_that_is_not_there(tmp_path):
    assert check_app(tmp_path / "Nothing.app") == [
        f"{tmp_path / 'Nothing.app'} does not exist"
    ]


# -- wiki publishing --------------------------------------------------------


def test_link_to_a_published_page_loses_its_extension():
    assert rewrite_links("[Install](Installation.md)", {"Installation"}) == (
        "[Install](Installation)"
    )


def test_an_anchor_survives_the_rewrite():
    assert rewrite_links("[S](Conventions.md#units)", {"Conventions"}) == (
        "[S](Conventions#units)"
    )


def test_a_link_to_an_unpublished_file_is_left_alone():
    """Rewriting it would turn a working link into a deliberate-looking 404."""
    text = "[code](../src/notes.md)"
    assert rewrite_links(text, {"Installation"}) == text


def test_a_page_not_being_published_is_left_alone():
    text = "[other](Elsewhere.md)"
    assert rewrite_links(text, {"Installation"}) == text


def test_an_external_url_is_untouched():
    text = "[spec](https://example.com/thing.md)"
    assert rewrite_links(text, {"thing"}) == text


def test_an_image_is_not_treated_as_a_link():
    text = "![diagram](Figure.md)"
    assert rewrite_links(text, {"Figure"}) == text


def test_publish_copies_and_reports_what_changed(tmp_path):
    docs, wiki = tmp_path / "docs", tmp_path / "wiki"
    docs.mkdir(), wiki.mkdir()
    (docs / "Home.md").write_text("see [Install](Installation.md)")
    (docs / "Installation.md").write_text("# Installation")

    changed = publish(docs, wiki)

    assert {p.name for p in changed} == {"Home.md", "Installation.md"}
    assert (wiki / "Home.md").read_text() == "see [Install](Installation)"


def test_publishing_twice_reports_nothing_the_second_time(tmp_path):
    docs, wiki = tmp_path / "docs", tmp_path / "wiki"
    docs.mkdir(), wiki.mkdir()
    (docs / "Home.md").write_text("# Home")
    publish(docs, wiki)
    assert publish(docs, wiki) == []


def test_a_dry_run_writes_nothing(tmp_path):
    docs, wiki = tmp_path / "docs", tmp_path / "wiki"
    docs.mkdir(), wiki.mkdir()
    (docs / "Home.md").write_text("# Home")

    changed = publish(docs, wiki, dry_run=True)

    assert changed
    assert not (wiki / "Home.md").exists()


def test_a_missing_wiki_checkout_says_how_to_clone_it(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "Home.md").write_text("# Home")
    with pytest.raises(SystemExit, match="git clone"):
        publish(docs, tmp_path / "absent.wiki")
