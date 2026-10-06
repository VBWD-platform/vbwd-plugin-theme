"""A test-only theme adapter: registers fake pages from ``on_enable``, as real adapters will.

It contributes its own templates (``fake_adapter_templates/``) and translations
(``fake_adapter_translations/``) and records every
:class:`ThemeRequest` its pages receive, so tests can assert the page contract.
Nothing here is registered in production code.
"""
from pathlib import Path
from typing import Any, Dict, List

from flask import Blueprint, jsonify, request

from vbwd.extensions import limiter
from vbwd.plugins.base import BasePlugin, PluginMetadata

from plugins.theme.theme.fragment_registry import ThemeFragment, ThemeFragmentRedirect
from plugins.theme.theme.page_registry import (
    ThemePage,
    resolve_theme_page_registry,
    resolve_theme_plugin,
)
from plugins.theme.theme.theme_api import ThemeApiError, call_api
from plugins.theme.theme.theme_registry import resolve_theme_registry
from plugins.theme.theme.theme_request import ThemeRequest

FAKE_ADAPTER_NAME = "fake_theme_adapter"
FAKE_OWNER_PLUGIN = "fake-fe-user-plugin"
FAKE_PAGE_PATH = "/fake-themed-page"
FAKE_ECHO_RULE = "/fake-items/<item_slug>"
FAKE_API_STATUS_RULE = "/fake-api-status/<int:status>"
FAKE_GATED_RULE = "/fake-gated/<item_slug>"
FAKE_LIMITED_PAGE_PATH = "/fake-limited"
FAKE_INNER_RATE_LIMIT = "1 per minute"
FAKE_LANGUAGE_PAGE_PATH = "/fake-language"
FAKE_TEMPLATES_DIRECTORY = Path(__file__).parent / "fake_adapter_templates"
FAKE_TRANSLATIONS_DIRECTORY = Path(__file__).parent / "fake_adapter_translations"
FAKE_API_PREFIX = "/api/v1/theme-test"
FAKE_ECHO_FRAGMENT_PATH = "/_render/_fragment/fake/echo"
FAKE_FORM_FRAGMENT_PATH = "/_render/_fragment/fake/form"
FAKE_STATUS_FRAGMENT_RULE = "/_render/_fragment/fake/status/<int:status>"
FAKE_REDIRECT_FRAGMENT_PATH = "/_render/_fragment/fake/redirect"

received_theme_requests: List[ThemeRequest] = []
# Statuses of the ThemeApiError each fake-limited render saw (one per failed call).
received_api_error_statuses: List[int] = []


def _record(theme_request: ThemeRequest) -> None:
    received_theme_requests.append(theme_request)


def _plain_page_context(theme_request: ThemeRequest) -> Dict[str, Any]:
    _record(theme_request)
    return {}


def _echo_context(theme_request: ThemeRequest) -> Dict[str, Any]:
    _record(theme_request)
    return {
        "echoed_path": theme_request.path,
        "item_slug": theme_request.view_args["item_slug"],
        "colour": theme_request.query_args.get("colour"),
        "echoed_language": theme_request.language,
    }


def _api_status_context(theme_request: ThemeRequest) -> Dict[str, Any]:
    status = theme_request.view_args["status"]
    body = call_api(theme_request, "GET", f"{FAKE_API_PREFIX}/status/{status}")
    return {"answer": body["answer"]}


def _gated_context(theme_request: ThemeRequest) -> Dict[str, Any]:
    _record(theme_request)
    return {"item_slug": theme_request.view_args["item_slug"]}


def _limited_context(theme_request: ThemeRequest) -> Dict[str, Any]:
    try:
        body = call_api(theme_request, "GET", f"{FAKE_API_PREFIX}/limited")
    except ThemeApiError as api_error:
        received_api_error_statuses.append(api_error.status)
        raise
    return {"answer": body["answer"]}


def _language_context(theme_request: ThemeRequest) -> Dict[str, Any]:
    inner_request = call_api(theme_request, "GET", f"{FAKE_API_PREFIX}/echo-language")
    context = {
        "echoed_language": theme_request.language,
        "inner_cookie": inner_request["cookie"],
        "inner_accept_language": inner_request["accept_language"],
    }
    page_language = theme_request.query_args.get("page_language")
    if page_language:
        context["page_language"] = page_language
    return context


FAKE_PAGES = (
    ThemePage(
        rule=FAKE_PAGE_PATH,
        endpoint="fake_themed_page",
        owner_fe_user_plugin=FAKE_OWNER_PLUGIN,
        priority=0,
        auth="public",
        template="fake/page.html.j2",
        build_context=_plain_page_context,
    ),
    ThemePage(
        rule=FAKE_ECHO_RULE,
        endpoint="fake_echo_page",
        owner_fe_user_plugin=FAKE_OWNER_PLUGIN,
        priority=0,
        auth="public",
        template="fake/echo.html.j2",
        build_context=_echo_context,
    ),
    ThemePage(
        rule=FAKE_API_STATUS_RULE,
        endpoint="fake_api_status_page",
        owner_fe_user_plugin=FAKE_OWNER_PLUGIN,
        priority=0,
        auth="public",
        template="fake/api_data.html.j2",
        build_context=_api_status_context,
    ),
    ThemePage(
        rule=FAKE_GATED_RULE,
        endpoint="fake_gated_page",
        owner_fe_user_plugin=FAKE_OWNER_PLUGIN,
        priority=0,
        auth="public",
        template="fake/gated.html.j2",
        build_context=_gated_context,
    ),
    ThemePage(
        rule=FAKE_LANGUAGE_PAGE_PATH,
        endpoint="fake_language_page",
        owner_fe_user_plugin=FAKE_OWNER_PLUGIN,
        priority=0,
        auth="public",
        template="fake/language.html.j2",
        build_context=_language_context,
    ),
    ThemePage(
        rule=FAKE_LIMITED_PAGE_PATH,
        endpoint="fake_limited_page",
        owner_fe_user_plugin=FAKE_OWNER_PLUGIN,
        priority=0,
        auth="public",
        template="fake/api_data.html.j2",
        build_context=_limited_context,
    ),
)


def _echo_fragment_context(theme_request: ThemeRequest) -> Dict[str, Any]:
    _record(theme_request)
    return {"q": theme_request.query_args.get("q")}


def _form_fragment_context(theme_request: ThemeRequest) -> Dict[str, Any]:
    _record(theme_request)
    return {"q": theme_request.query_args.get("name")}


def _status_fragment_context(theme_request: ThemeRequest) -> Dict[str, Any]:
    _api_status_context(theme_request)
    return {"q": "unreachable"}


def _redirect_fragment_context(theme_request: ThemeRequest) -> Dict[str, Any]:
    raise ThemeFragmentRedirect(theme_request.query_args.get("to") or "/")


FAKE_FRAGMENTS = (
    ThemeFragment(
        rule=FAKE_ECHO_FRAGMENT_PATH,
        endpoint="fake_echo_fragment",
        owner_fe_user_plugin=FAKE_OWNER_PLUGIN,
        template="fake/fragment.html.j2",
        build_context=_echo_fragment_context,
    ),
    ThemeFragment(
        rule=FAKE_FORM_FRAGMENT_PATH,
        endpoint="fake_form_fragment",
        owner_fe_user_plugin=FAKE_OWNER_PLUGIN,
        template="fake/fragment.html.j2",
        build_context=_form_fragment_context,
        methods=("POST",),
    ),
    ThemeFragment(
        rule=FAKE_STATUS_FRAGMENT_RULE,
        endpoint="fake_status_fragment",
        owner_fe_user_plugin=FAKE_OWNER_PLUGIN,
        template="fake/fragment.html.j2",
        build_context=_status_fragment_context,
    ),
    ThemeFragment(
        rule=FAKE_REDIRECT_FRAGMENT_PATH,
        endpoint="fake_redirect_fragment",
        owner_fe_user_plugin=FAKE_OWNER_PLUGIN,
        template="fake/fragment.html.j2",
        build_context=_redirect_fragment_context,
        methods=("POST",),
    ),
)


def build_fake_api_blueprint() -> Blueprint:
    """Test-only ``/api/v1`` routes the fake pages call through core C2."""
    blueprint = Blueprint("theme_test_api", __name__)

    @blueprint.route(f"{FAKE_API_PREFIX}/status/<int:status>")
    def respond_with_status(status: int):
        return jsonify({"answer": 42, "error": f"inner status {status}"}), status

    @blueprint.route(f"{FAKE_API_PREFIX}/echo-language")
    def echo_language():
        return jsonify(
            {
                "cookie": request.cookies.get("vbwd_lang"),
                "accept_language": request.headers.get("Accept-Language"),
            }
        )

    @blueprint.route(f"{FAKE_API_PREFIX}/limited")
    @limiter.limit(FAKE_INNER_RATE_LIMIT)
    def limited():
        return jsonify({"answer": 42})

    return blueprint


class FakeThemeAdapterPlugin(BasePlugin):
    """Registers the fake pages and contributes the fake templates from on_enable."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name=FAKE_ADAPTER_NAME,
            version="1.0.0",
            author="Test",
            description="Test-only theme adapter",
            dependencies=["theme"],
        )

    def on_enable(self) -> None:
        theme_registry = resolve_theme_registry()
        theme_registry.add_contributed_template_path(FAKE_TEMPLATES_DIRECTORY)
        theme_registry.add_contributed_translation_path(FAKE_TRANSLATIONS_DIRECTORY)
        page_registry = resolve_theme_page_registry()
        for page in FAKE_PAGES:
            page_registry.register(page)
        fragment_registry = resolve_theme_plugin().fragment_registry
        for fragment in FAKE_FRAGMENTS:
            fragment_registry.register(fragment)
