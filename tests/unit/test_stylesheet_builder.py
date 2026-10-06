"""S152-03 — StylesheetBuilder (D8): CSS chain + one merged ``:root`` token block."""
import hashlib
import json
from pathlib import Path

import pytest

from plugins.theme.theme.stylesheet import Stylesheet, StylesheetBuilder
from plugins.theme.theme.theme_registry import ThemeDescriptor

PUBLIC_SURFACE = "public"


def _theme(tmp_path: Path, slug: str, parent=None) -> ThemeDescriptor:
    root = tmp_path / slug
    (root / "templates").mkdir(parents=True)
    return ThemeDescriptor(slug=slug, name=slug.title(), parent=parent, root=root)


def _write_css(descriptor: ThemeDescriptor, relative_path: str, css: str) -> Path:
    css_path = descriptor.root / "static" / relative_path
    css_path.parent.mkdir(parents=True, exist_ok=True)
    css_path.write_text(css, encoding="utf-8")
    return css_path


def _write_tokens(descriptor: ThemeDescriptor, tokens: dict) -> None:
    (descriptor.root / "tokens.json").write_text(json.dumps(tokens), encoding="utf-8")


@pytest.fixture
def basic(tmp_path) -> ThemeDescriptor:
    return _theme(tmp_path, "basic")


@pytest.fixture
def child(tmp_path) -> ThemeDescriptor:
    return _theme(tmp_path, "acme", parent="basic")


def _build(*descriptors: ThemeDescriptor) -> Stylesheet:
    return StylesheetBuilder().build(list(descriptors), PUBLIC_SURFACE)


def test_shared_css_comes_before_surface_css_within_a_theme(basic):
    _write_css(basic, "public/a-page.css", ".page{}")
    _write_css(basic, "_shared/z-base.css", ".base{}")

    css_text = _build(basic).css_text

    assert css_text.index(".base{}") < css_text.index(".page{}")


def test_files_of_one_directory_are_sorted_by_filename(basic):
    _write_css(basic, "_shared/b.css", ".second{}")
    _write_css(basic, "_shared/a.css", ".first{}")

    css_text = _build(basic).css_text

    assert css_text.index(".first{}") < css_text.index(".second{}")


def test_basic_comes_before_the_child_theme(basic, child):
    _write_css(child, "_shared/child.css", ".child-shared{}")
    _write_css(basic, "public/basic.css", ".basic-public{}")

    css_text = _build(basic, child).css_text

    assert css_text.index(".basic-public{}") < css_text.index(".child-shared{}")


def test_only_the_requested_surface_and_direct_css_files_are_included(basic):
    _write_css(basic, "other/hidden.css", ".other-surface{}")
    _write_css(basic, "_shared/js/not-css.js", "var script;")
    _write_css(basic, "_shared/nested/deep.css", ".nested{}")
    _write_css(basic, "_shared/base.css", ".base{}")

    css_text = _build(basic).css_text

    assert ".base{}" in css_text
    assert ".other-surface{}" not in css_text
    assert "var script;" not in css_text
    assert ".nested{}" not in css_text


def test_tokens_merge_into_one_root_block_after_the_css(basic, child):
    _write_css(basic, "_shared/base.css", ".base{}")
    _write_tokens(basic, {"--vbwd-color-primary": "#111", "--vbwd-radius": "4px"})
    _write_tokens(child, {"--vbwd-color-primary": "#0a7f6f", "--vbwd-gap": "8px"})

    css_text = _build(basic, child).css_text

    assert css_text.count(":root") == 1
    assert css_text.index(".base{}") < css_text.index(":root")
    assert css_text.count("--vbwd-color-primary") == 1
    assert "--vbwd-color-primary: #0a7f6f;" in css_text
    assert "--vbwd-radius: 4px;" in css_text
    assert "--vbwd-gap: 8px;" in css_text


def test_token_order_is_deterministic_by_name(basic, child):
    _write_tokens(basic, {"--vbwd-z": "1", "--vbwd-a": "2"})
    _write_tokens(child, {"--vbwd-m": "3"})

    css_text = _build(basic, child).css_text

    positions = [css_text.index(name) for name in ("--vbwd-a", "--vbwd-m", "--vbwd-z")]
    assert positions == sorted(positions)
    assert _build(basic, child) == _build(basic, child)


def test_content_hash_is_the_first_sixteen_hex_of_the_css_sha256(basic):
    _write_css(basic, "_shared/base.css", ".base{}")

    stylesheet = _build(basic)

    expected = hashlib.sha256(stylesheet.css_text.encode("utf-8")).hexdigest()[:16]
    assert stylesheet.content_hash == expected
    css_text, content_hash = stylesheet
    assert (css_text, content_hash) == (stylesheet.css_text, expected)


def test_content_hash_changes_when_a_file_changes(basic):
    css_path = _write_css(basic, "_shared/base.css", ".base{color:red}")
    before = _build(basic).content_hash

    css_path.write_text(".base{color:blue}", encoding="utf-8")

    assert _build(basic).content_hash != before


def test_content_hash_changes_when_a_token_changes(basic):
    _write_tokens(basic, {"--vbwd-gap": "4px"})
    before = _build(basic).content_hash

    _write_tokens(basic, {"--vbwd-gap": "8px"})

    assert _build(basic).content_hash != before


def _contributed_directory(tmp_path: Path, name: str, relative_path: str, css: str):
    """An adapter's stylesheet directory: ``_shared/*.css`` + ``<surface>/*.css``."""
    directory = tmp_path / "contributed" / name
    css_path = directory / relative_path
    css_path.parent.mkdir(parents=True, exist_ok=True)
    css_path.write_text(css, encoding="utf-8")
    return directory


def test_order_is_basic_then_contributed_then_child_then_tokens(tmp_path, basic, child):
    _write_css(basic, "public/basic.css", ".basic{}")
    _write_css(child, "_shared/child.css", ".child{}")
    _write_tokens(basic, {"--vbwd-gap": "4px"})
    shop = _contributed_directory(tmp_path, "shop", "public/shop.css", ".shop{}")
    cms = _contributed_directory(tmp_path, "cms", "_shared/cms.css", ".cms{}")

    css_text = (
        StylesheetBuilder()
        .build([basic, child], PUBLIC_SURFACE, contributed_stylesheet_paths=[shop, cms])
        .css_text
    )

    positions = [
        css_text.index(marker)
        for marker in (".basic{}", ".shop{}", ".cms{}", ".child{}", ":root")
    ]
    assert positions == sorted(positions)


def test_contributed_css_follows_the_surface_rules(tmp_path, basic):
    cms = _contributed_directory(tmp_path, "cms", "public/b.css", ".public-b{}")
    _contributed_directory(tmp_path, "cms", "public/a.css", ".public-a{}")
    _contributed_directory(tmp_path, "cms", "_shared/z.css", ".shared-z{}")
    _contributed_directory(tmp_path, "cms", "admin/x.css", ".other-surface{}")

    css_text = (
        StylesheetBuilder()
        .build([basic], PUBLIC_SURFACE, contributed_stylesheet_paths=[cms])
        .css_text
    )

    positions = [
        css_text.index(marker)
        for marker in (".shared-z{}", ".public-a{}", ".public-b{}")
    ]
    assert positions == sorted(positions)
    assert ".other-surface{}" not in css_text


def test_without_contributions_the_stylesheet_is_unchanged(basic, child):
    _write_css(basic, "_shared/base.css", ".base{}")
    _write_css(child, "public/child.css", ".child{}")

    with_empty_contributions = StylesheetBuilder().build(
        [basic, child], PUBLIC_SURFACE, contributed_stylesheet_paths=[]
    )

    assert with_empty_contributions == _build(basic, child)
