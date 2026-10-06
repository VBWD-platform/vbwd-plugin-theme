"""``GET /_render/_fragment/regions?path=<public url>`` — personalised regions (S152 D12).

The runtime calls this with ``Authorization: Bearer <auth_token>`` after an
anonymous page load. The endpoint matches ``path`` against the app's own route
table (theme page endpoints only), applies the same fe-user owner gate as the
page, resolves the viewer from ``GET /api/v1/user/profile`` through core C2,
re-renders the SAME page for that viewer and returns ONLY the region contents:
``{"regions": {"r1": "<html>", …}}``. Re-rendering (rather than serialising
region contexts) keeps one mechanism, and inner API calls run with the user's
token, so the domain API's own access rules apply.

Authentication: core ``require_auth`` (a bad or absent token never reaches the
page code); a profile refusal (401/403) is also a 401 so the runtime ends the
session. Always ``Cache-Control: no-store``.
"""
from dataclasses import replace
from types import MappingProxyType
from typing import Any, Callable, Dict, Mapping, Optional, Tuple
from urllib.parse import parse_qsl, urlsplit

from flask import Response, current_app, jsonify, request
from werkzeug.datastructures import ImmutableMultiDict
from werkzeug.exceptions import HTTPException

from vbwd.middleware.auth import require_auth

from .fe_user_manifest import FeUserPluginManifest
from .language_resolver import ThemeLanguageResolver
from .page_registry import THEME_BLUEPRINT_NAME, ThemePage, ThemePageRegistry
from .page_rendering import build_page_context
from .renderer import ThemeRenderer
from .theme_api import ThemeApiError, call_api, themed_error_status
from .theme_request import ThemeRequest
from .viewer import ANONYMOUS_VIEWER, viewer_from_profile

REGIONS_PATH = "/_render/_fragment/regions"
USER_PROFILE_PATH = "/api/v1/user/profile"
PATH_QUERY_PARAMETER = "path"
IDS_QUERY_PARAMETER = "ids"
IDS_SEPARATOR = ","
NO_STORE = "no-store"
OK = 200
BAD_REQUEST = 400
UNAUTHORIZED = 401
NOT_FOUND = 404
PROFILE_REFUSAL_STATUSES = (401, 403)

PageMatch = Tuple[ThemePage, Mapping[str, Any]]


def _no_store_json(payload: dict, status: int) -> Response:
    response = jsonify(payload)
    response.status_code = status
    response.headers["Cache-Control"] = NO_STORE
    return response


def _error(message: str, status: int) -> Response:
    return _no_store_json({"error": message}, status)


def _match_page(
    pages_by_endpoint: Dict[str, ThemePage], path: str
) -> Optional[PageMatch]:
    """The theme page the app would route ``path`` to, else ``None``."""
    url_adapter = current_app.url_map.bind_to_environ(request.environ)
    try:
        endpoint, view_args = url_adapter.match(path, method="GET")
    except HTTPException:
        return None
    page = pages_by_endpoint.get(endpoint)
    return (page, view_args) if page is not None else None


def _select_regions(
    regions: Dict[str, str], requested_ids: Optional[str]
) -> Optional[Dict[str, str]]:
    """All regions, or only ``ids``; ``None`` when an id is not on the page."""
    if not requested_ids:
        return regions
    wanted_ids = [region_id.strip() for region_id in requested_ids.split(IDS_SEPARATOR)]
    if any(region_id not in regions for region_id in wanted_ids):
        return None
    return {region_id: regions[region_id] for region_id in wanted_ids}


def _target_request(target_url: str, view_args: Mapping[str, Any]) -> ThemeRequest:
    """The page request for ``target_url``, still anonymous, carrying this request's headers."""
    split_url = urlsplit(target_url)
    return ThemeRequest(
        path=split_url.path,
        view_args=MappingProxyType(dict(view_args)),
        query_args=ImmutableMultiDict(
            parse_qsl(split_url.query, keep_blank_values=True)
        ),
        viewer=ANONYMOUS_VIEWER,
        http_request=request,
    )


def _render_regions_for_viewer(
    page: ThemePage,
    anonymous_request: ThemeRequest,
    renderer: ThemeRenderer,
    language_resolver: ThemeLanguageResolver,
) -> Response:
    try:
        profile = call_api(anonymous_request, "GET", USER_PROFILE_PATH)
    except ThemeApiError as profile_error:
        if profile_error.status in PROFILE_REFUSAL_STATUSES:
            return _error("session is not valid", UNAUTHORIZED)
        return _error("viewer unavailable", themed_error_status(profile_error.status))
    theme_request = replace(anonymous_request, viewer=viewer_from_profile(profile))
    try:
        context = build_page_context(page, theme_request, language_resolver)
    except ThemeApiError as api_error:
        return _error("page data unavailable", themed_error_status(api_error.status))
    rendered = renderer.render_with_regions(
        page.template, context, viewer=theme_request.viewer
    )
    selected_regions = _select_regions(
        rendered.regions, request.args.get(IDS_QUERY_PARAMETER)
    )
    if selected_regions is None:
        return _error("a requested region id is not on this page", BAD_REQUEST)
    return _no_store_json({"regions": selected_regions}, OK)


def build_regions_view(
    registry: ThemePageRegistry,
    manifest: FeUserPluginManifest,
    renderer: ThemeRenderer,
    language_resolver: ThemeLanguageResolver,
) -> Callable:
    pages_by_endpoint = {
        f"{THEME_BLUEPRINT_NAME}.{page.endpoint}": page for page in registry.pages()
    }

    @require_auth
    def regions():
        target_url = request.args.get(PATH_QUERY_PARAMETER)
        if not target_url:
            return _error("the 'path' query parameter is required", BAD_REQUEST)
        match = _match_page(pages_by_endpoint, urlsplit(target_url).path)
        if match is None or not manifest.is_enabled(match[0].owner_fe_user_plugin):
            return _error("not a themed page", NOT_FOUND)
        page, view_args = match
        target_request = language_resolver.with_pre_context_language(
            _target_request(target_url, view_args)
        )
        return _render_regions_for_viewer(
            page, target_request, renderer, language_resolver
        )

    return regions
