"""S152-03 — ThemeStaticAssets: chain-resolved static files and their hashed URLs."""
from pathlib import Path

import pytest

from plugins.theme.theme.static_assets import ThemeStaticAssets
from plugins.theme.theme.stylesheet import content_hash
from plugins.theme.theme.theme_registry import ThemeDescriptor, ThemeRegistry


def _register(registry: ThemeRegistry, tmp_path: Path, slug: str, parent=None):
    root = tmp_path / slug
    (root / "templates").mkdir(parents=True)
    registry.register(ThemeDescriptor(slug=slug, name=slug, parent=parent, root=root))
    return root


def _write_static(theme_root: Path, relative_path: str, content: str) -> Path:
    static_path = theme_root / "static" / relative_path
    static_path.parent.mkdir(parents=True, exist_ok=True)
    static_path.write_text(content, encoding="utf-8")
    return static_path


@pytest.fixture
def registry() -> ThemeRegistry:
    return ThemeRegistry()


@pytest.fixture
def basic_root(registry, tmp_path) -> Path:
    return _register(registry, tmp_path, "basic")


@pytest.fixture
def child_root(registry, tmp_path, basic_root) -> Path:
    return _register(registry, tmp_path, "acme", parent="basic")


def test_resolve_finds_a_file_in_the_theme_itself(registry, basic_root):
    static_path = _write_static(basic_root, "_shared/js/app.js", "x")

    assert (
        ThemeStaticAssets(registry).resolve("basic", "_shared/js/app.js") == static_path
    )


def test_resolve_falls_back_through_the_parent_chain(registry, basic_root, child_root):
    static_path = _write_static(basic_root, "_shared/js/app.js", "x")

    assert (
        ThemeStaticAssets(registry).resolve("acme", "_shared/js/app.js") == static_path
    )


def test_resolve_prefers_the_child_file(registry, basic_root, child_root):
    _write_static(basic_root, "logo.svg", "basic")
    child_path = _write_static(child_root, "logo.svg", "child")

    assert ThemeStaticAssets(registry).resolve("acme", "logo.svg") == child_path


@pytest.mark.parametrize(
    "asset_path",
    ["../templates/secret.html.j2", "../../outside.txt", "/etc/passwd", "a/../../x"],
)
def test_resolve_refuses_traversal(registry, basic_root, tmp_path, asset_path):
    (basic_root / "templates" / "secret.html.j2").write_text("secret")
    (tmp_path / "outside.txt").write_text("outside")

    assert ThemeStaticAssets(registry).resolve("basic", asset_path) is None


def test_resolve_unknown_theme_or_missing_file_is_none(registry, basic_root):
    _write_static(basic_root, "_shared", "")  # a file named like the directory
    assets = ThemeStaticAssets(registry)

    assert assets.resolve("ghost", "_shared") is None
    assert assets.resolve("basic", "missing.css") is None


def test_resolve_refuses_a_directory(registry, basic_root):
    _write_static(basic_root, "_shared/js/app.js", "x")

    assert ThemeStaticAssets(registry).resolve("basic", "_shared/js") is None


def test_asset_url_carries_the_file_content_hash(registry, basic_root):
    _write_static(basic_root, "_shared/js/app.js", "console.log(1)")

    url = ThemeStaticAssets(registry).asset_url("basic", "_shared/js/app.js")

    expected_version = content_hash(b"console.log(1)")
    assert url == f"/_render/_theme/static/basic/_shared/js/app.js?v={expected_version}"


def test_asset_url_keeps_the_active_slug_for_an_inherited_file(
    registry, basic_root, child_root
):
    _write_static(basic_root, "_shared/js/app.js", "x")

    url = ThemeStaticAssets(registry).asset_url("acme", "_shared/js/app.js")

    assert url.startswith("/_render/_theme/static/acme/_shared/js/app.js?v=")


def test_asset_url_of_a_missing_file_has_no_version(registry, basic_root):
    url = ThemeStaticAssets(registry).asset_url("basic", "missing.js")

    assert url == "/_render/_theme/static/basic/missing.js"


def test_stylesheet_is_built_basic_first_for_the_public_surface(
    registry, basic_root, child_root
):
    _write_static(child_root, "public/child.css", ".child{}")
    _write_static(basic_root, "public/basic.css", ".basic{}")

    css_text = ThemeStaticAssets(registry).stylesheet("acme").css_text

    assert css_text.index(".basic{}") < css_text.index(".child{}")


def test_stylesheet_url_carries_the_stylesheet_hash(registry, basic_root):
    _write_static(basic_root, "_shared/base.css", ".base{}")
    assets = ThemeStaticAssets(registry)

    url = assets.stylesheet_url("basic")

    assert url == (
        f"/_render/_theme/public/theme.css?v={assets.stylesheet('basic').content_hash}"
    )


def test_stylesheet_puts_contributed_css_between_basic_and_the_child(
    registry, basic_root, child_root, tmp_path
):
    _write_static(basic_root, "public/basic.css", ".basic{}")
    _write_static(child_root, "public/child.css", ".child{}")
    contributed = tmp_path / "adapter"
    (contributed / "public").mkdir(parents=True)
    (contributed / "public" / "adapter.css").write_text(".adapter{}", encoding="utf-8")
    registry.add_contributed_stylesheet_path(contributed)

    css_text = ThemeStaticAssets(registry).stylesheet("acme").css_text

    assert (
        css_text.index(".basic{}")
        < css_text.index(".adapter{}")
        < css_text.index(".child{}")
    )
