"""S152-03 — the asset routes: ``theme.css`` and the traversal-proof static route."""
from pathlib import Path

import pytest
from flask import Flask

from plugins.theme.theme.fe_user_manifest import FeUserPluginManifest
from plugins.theme.theme.fragment_registry import ThemeFragmentRegistry
from plugins.theme.theme.page_registry import ThemePageRegistry
from plugins.theme.theme.renderer import ThemeRenderer
from plugins.theme.theme.language_policy import CoreLanguagePolicy
from plugins.theme.theme.language_resolver import ThemeLanguageResolver
from plugins.theme.theme.routes import build_theme_blueprint
from plugins.theme.theme.static_assets import ThemeStaticAssets
from plugins.theme.theme.stylesheet import content_hash
from plugins.theme.theme.theme_registry import ThemeDescriptor, ThemeRegistry

STYLESHEET_PATH = "/_render/_theme/public/theme.css"
STATIC_PREFIX = "/_render/_theme/static"
IMMUTABLE = "public, max-age=31536000, immutable"
SHORT_LIVED = "public, max-age=300"
RUNTIME_SCRIPT = "_shared/js/runtime.js"
RUNTIME_SOURCE = b"window.runtime = 1;"


def _register(registry: ThemeRegistry, tmp_path: Path, slug: str, parent=None):
    root = tmp_path / slug
    (root / "templates").mkdir(parents=True)
    registry.register(ThemeDescriptor(slug=slug, name=slug, parent=parent, root=root))
    return root


def _write_static(theme_root: Path, relative_path: str, content: bytes) -> None:
    static_path = theme_root / "static" / relative_path
    static_path.parent.mkdir(parents=True, exist_ok=True)
    static_path.write_bytes(content)


@pytest.fixture
def themes(tmp_path):
    registry = ThemeRegistry()
    basic_root = _register(registry, tmp_path, "basic")
    child_root = _register(registry, tmp_path, "acme", parent="basic")
    _write_static(basic_root, "_shared/base.css", b".basic{}")
    _write_static(child_root, "public/child.css", b".child{}")
    _write_static(basic_root, RUNTIME_SCRIPT, RUNTIME_SOURCE)
    (basic_root / "templates" / "secret.html.j2").write_text("secret")
    return registry


def _client(registry: ThemeRegistry, active_slug: str = "basic"):
    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(
        build_theme_blueprint(
            ThemePageRegistry(),
            FeUserPluginManifest(),
            ThemeRenderer(registry, lambda: active_slug),
            ThemeLanguageResolver(CoreLanguagePolicy()),
            ThemeFragmentRegistry(),
        )
    )
    return app.test_client()


def _stylesheet_hash(registry: ThemeRegistry, active_slug: str = "basic") -> str:
    return ThemeStaticAssets(registry).stylesheet(active_slug).content_hash


def test_theme_css_serves_the_active_chain_as_css_without_the_render_header(themes):
    response = _client(themes, active_slug="acme").get(STYLESHEET_PATH)

    assert response.status_code == 200
    assert response.mimetype == "text/css"
    body = response.get_data(as_text=True)
    assert body == ThemeStaticAssets(themes).stylesheet("acme").css_text
    assert body.index(".basic{}") < body.index(".child{}")


def test_theme_css_has_a_strong_etag_equal_to_the_content_hash(themes):
    response = _client(themes).get(STYLESHEET_PATH)

    assert response.headers["ETag"] == f'"{_stylesheet_hash(themes)}"'


def test_theme_css_if_none_match_returns_304(themes):
    response = _client(themes).get(
        STYLESHEET_PATH, headers={"If-None-Match": f'"{_stylesheet_hash(themes)}"'}
    )

    assert response.status_code == 304
    assert response.get_data() == b""


def test_theme_css_with_the_matching_version_is_immutable(themes):
    response = _client(themes).get(f"{STYLESHEET_PATH}?v={_stylesheet_hash(themes)}")

    assert response.headers["Cache-Control"] == IMMUTABLE


@pytest.mark.parametrize("query", ["", "?v=stale0000000000"])
def test_theme_css_without_the_matching_version_is_short_lived(themes, query):
    response = _client(themes).get(f"{STYLESHEET_PATH}{query}")

    assert response.headers["Cache-Control"] == SHORT_LIVED


def test_static_serves_an_inherited_file_for_the_child_theme(themes):
    response = _client(themes).get(f"{STATIC_PREFIX}/acme/{RUNTIME_SCRIPT}")

    assert response.status_code == 200
    assert response.get_data() == RUNTIME_SOURCE
    assert response.headers["ETag"] == f'"{content_hash(RUNTIME_SOURCE)}"'


def test_static_with_the_matching_version_is_immutable(themes):
    version = content_hash(RUNTIME_SOURCE)

    response = _client(themes).get(
        f"{STATIC_PREFIX}/basic/{RUNTIME_SCRIPT}?v={version}"
    )

    assert response.headers["Cache-Control"] == IMMUTABLE


def test_static_without_a_version_is_short_lived(themes):
    response = _client(themes).get(f"{STATIC_PREFIX}/basic/{RUNTIME_SCRIPT}")

    assert response.headers["Cache-Control"] == SHORT_LIVED


def test_static_if_none_match_returns_304(themes):
    response = _client(themes).get(
        f"{STATIC_PREFIX}/basic/{RUNTIME_SCRIPT}",
        headers={"If-None-Match": f'"{content_hash(RUNTIME_SOURCE)}"'},
    )

    assert response.status_code == 304


def test_static_unknown_theme_is_404(themes):
    assert (
        _client(themes).get(f"{STATIC_PREFIX}/ghost/{RUNTIME_SCRIPT}").status_code
        == 404
    )


def test_static_missing_file_is_404(themes):
    assert _client(themes).get(f"{STATIC_PREFIX}/basic/missing.js").status_code == 404


@pytest.mark.parametrize(
    "traversal_path",
    [
        "basic/../templates/secret.html.j2",
        "basic/%2e%2e/templates/secret.html.j2",
        "basic/..%2ftemplates/secret.html.j2",
        "basic/%2fetc/passwd",
    ],
)
def test_static_traversal_is_404(themes, traversal_path):
    # werkzeug merges a doubled slash with a 308 first; the final answer counts.
    response = _client(themes).get(
        f"{STATIC_PREFIX}/{traversal_path}", follow_redirects=True
    )

    assert response.status_code == 404
    assert b"secret" not in response.get_data()
