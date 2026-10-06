"""The theme blueprint (W2): page routes at their public paths, the mode probe and assets.

Built only in ``theme`` mode. Every page answers only when nginx marked the
request with ``X-VBWD-Render: 1`` and its owner fe-user plugin is enabled;
otherwise it 404s so nginx falls back to the SPA. The probe, the asset routes
(``theme.css``, static files) and the adapters' fragments need no header.
"""
from types import MappingProxyType
from typing import Callable

from flask import Blueprint, Response, abort, jsonify, request, send_from_directory
from werkzeug.wrappers import Response as BaseResponse

from vbwd.extensions import limiter

from .fe_user_manifest import FeUserPluginManifest
from .fragment_registry import ThemeFragmentRegistry
from .fragments import build_fragment_view
from .frontend_mode import FrontendMode
from .language_resolver import ThemeLanguageResolver
from .page_registry import THEME_BLUEPRINT_NAME, ThemePage, ThemePageRegistry
from .page_rendering import render_page
from .regions import REGIONS_PATH, build_regions_view
from .renderer import ThemeRenderer
from .static_assets import (
    THEME_STATIC_URL_PREFIX,
    THEME_STYLESHEET_PATH,
    VERSION_QUERY_PARAMETER,
    ThemeStaticAssets,
    file_content_hash,
)
from .theme_request import ThemeRequest
from .viewer import ANONYMOUS_VIEWER

MODE_PROBE_PATH = "/_render/_theme/mode"
RENDER_REQUEST_HEADER = "X-VBWD-Render"
RENDER_REQUEST_HEADER_VALUE = "1"
NOT_FOUND = 404
STATIC_ASSET_RULE = f"{THEME_STATIC_URL_PREFIX}/<theme_slug>/<path:asset_path>"
CSS_MIMETYPE = "text/css"
ONE_YEAR_SECONDS = 31536000
SHORT_LIVED_SECONDS = 300
IMMUTABLE_CACHE_CONTROL = f"public, max-age={ONE_YEAR_SECONDS}, immutable"
SHORT_LIVED_CACHE_CONTROL = f"public, max-age={SHORT_LIVED_SECONDS}"


def _guarded_page_view(
    page: ThemePage,
    manifest: FeUserPluginManifest,
    renderer: ThemeRenderer,
    language_resolver: ThemeLanguageResolver,
) -> Callable:
    def view(**view_args):
        if request.headers.get(RENDER_REQUEST_HEADER) != RENDER_REQUEST_HEADER_VALUE:
            abort(NOT_FOUND)
        if not manifest.is_enabled(page.owner_fe_user_plugin):
            abort(NOT_FOUND)
        # D4 — a navigation carries no bearer: the page always renders anonymously.
        theme_request = ThemeRequest(
            path=request.path,
            view_args=MappingProxyType(dict(view_args)),
            query_args=request.args,
            viewer=ANONYMOUS_VIEWER,
            http_request=request,
        )
        return render_page(
            page,
            language_resolver.with_pre_context_language(theme_request),
            renderer,
            language_resolver,
        )

    view.__name__ = page.endpoint
    return view


def _frontend_mode_probe():
    return jsonify({"mode": FrontendMode.THEME.value})


def _versioned_caching(response: BaseResponse, content_hash: str) -> BaseResponse:
    """Strong ETag = content hash; immutable only when ``?v=`` names this content."""
    response.set_etag(content_hash)
    if request.args.get(VERSION_QUERY_PARAMETER) == content_hash:
        response.headers["Cache-Control"] = IMMUTABLE_CACHE_CONTROL
    else:
        response.headers["Cache-Control"] = SHORT_LIVED_CACHE_CONTROL
    return response.make_conditional(request)


def _theme_stylesheet_view(
    static_assets: ThemeStaticAssets, read_active_theme_slug: Callable[[], str]
) -> Callable:
    def theme_stylesheet():
        stylesheet = static_assets.stylesheet(read_active_theme_slug())
        response = Response(stylesheet.css_text, mimetype=CSS_MIMETYPE)
        return _versioned_caching(response, stylesheet.content_hash)

    return theme_stylesheet


def _static_asset_view(static_assets: ThemeStaticAssets) -> Callable:
    def static_asset(theme_slug: str, asset_path: str):
        resolved_path = static_assets.resolve(theme_slug, asset_path)
        if resolved_path is None:
            abort(NOT_FOUND)
        response = send_from_directory(
            resolved_path.parent, resolved_path.name, etag=False
        )
        return _versioned_caching(response, file_content_hash(resolved_path))

    return static_asset


def build_theme_blueprint(
    registry: ThemePageRegistry,
    manifest: FeUserPluginManifest,
    renderer: ThemeRenderer,
    language_resolver: ThemeLanguageResolver,
    fragment_registry: ThemeFragmentRegistry,
) -> Blueprint:
    blueprint = Blueprint(THEME_BLUEPRINT_NAME, __name__)
    blueprint.add_url_rule(
        MODE_PROBE_PATH, "frontend_mode", _frontend_mode_probe, methods=["GET"]
    )
    blueprint.add_url_rule(
        THEME_STYLESHEET_PATH,
        "theme_stylesheet",
        _theme_stylesheet_view(renderer.static_assets, renderer.active_theme_slug),
        methods=["GET"],
    )
    blueprint.add_url_rule(
        STATIC_ASSET_RULE,
        "static_asset",
        _static_asset_view(renderer.static_assets),
        methods=["GET"],
    )
    blueprint.add_url_rule(
        REGIONS_PATH,
        "regions",
        build_regions_view(registry, manifest, renderer, language_resolver),
        methods=["GET"],
    )
    for fragment in fragment_registry.fragments():
        blueprint.add_url_rule(
            fragment.rule,
            fragment.endpoint,
            build_fragment_view(fragment, manifest, renderer, language_resolver),
            methods=list(fragment.methods),
        )
    for page in registry.pages():
        blueprint.add_url_rule(
            page.rule,
            page.endpoint,
            _guarded_page_view(page, manifest, renderer, language_resolver),
            methods=["GET"],
        )
    # Page navigations, the probe and assets are not API calls; the inner C2 API calls
    # a page makes keep their own limits.
    limiter.exempt(blueprint)
    return blueprint
