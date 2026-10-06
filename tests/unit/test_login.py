"""S152-07 A — the themed ``/login`` (fe-user core ``Login.vue``).

The page renders the same form (testids ``email``, ``password``,
``login-button``; copy from the SPA's ``login.*`` keys). The htmx fragment posts
to ``POST /api/v1/auth/login`` through ``call_api`` and answers either the SPA's
``error-message`` or a ``data-vbwd-session`` directive the runtime turns into
the SPA's localStorage keys plus the navigation to ``redirect`` (same-origin
path only) or ``/dashboard``.
"""
import json
import re
from types import MappingProxyType

import pytest
from flask import Flask

from plugins.theme import ThemePlugin
from plugins.theme.theme import login
from plugins.theme.theme.fe_user_manifest import CORE_OWNER
from plugins.theme.theme.login import (
    DASHBOARD_PATH,
    LOGIN_API_PATH,
    LOGIN_FRAGMENT_PATH,
    LOGIN_PAGE_PATH,
    login_page_context,
    login_result_context,
    safe_redirect_target,
)
from plugins.theme.theme.page_registry import PUBLIC_PAGE
from plugins.theme.theme.theme_api import ThemeApiError


@pytest.fixture(autouse=True)
def isolated_var_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("VBWD_VAR_DIR", str(tmp_path / "var"))


class FakeThemeRequest:
    def __init__(self, query=None):
        self.query_args = MappingProxyType(dict(query or {}))
        self.http_request = None


@pytest.fixture
def enabled_plugin() -> ThemePlugin:
    plugin = ThemePlugin()
    plugin.on_enable()
    return plugin


def _render(plugin, template, context):
    app = Flask(__name__)
    app.testing = True
    with app.app_context():
        return plugin.renderer.render(
            template, {"language": "en", "default_language": "en", **context}
        )


@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, None),
        ("", None),
        ("/shop/cart?x=1", "/shop/cart?x=1"),
        ("/pay/stripe?invoice=abc", "/pay/stripe?invoice=abc"),
        ("/login", DASHBOARD_PATH),
        ("/login?redirect=/x", DASHBOARD_PATH),
        ("https://evil.example/", DASHBOARD_PATH),
        ("//evil.example/x", DASHBOARD_PATH),
        ("/\\evil.example", DASHBOARD_PATH),
        ("javascript:alert(1)", DASHBOARD_PATH),
        ("shop", DASHBOARD_PATH),
    ],
)
def test_redirect_target_is_a_same_origin_path_never_back_into_login(raw, expected):
    assert safe_redirect_target(raw) == expected


def test_enable_registers_the_login_page_for_the_core_owner(enabled_plugin):
    pages = [
        page for page in enabled_plugin.page_registry.pages() if page.rule == "/login"
    ]

    assert len(pages) == 1
    assert pages[0].owner_fe_user_plugin == CORE_OWNER
    assert pages[0].auth == PUBLIC_PAGE
    assert LOGIN_PAGE_PATH == "/login"


def test_enable_registers_the_login_fragment_as_a_post(enabled_plugin):
    fragments = [
        fragment
        for fragment in enabled_plugin.fragment_registry.fragments()
        if fragment.rule == LOGIN_FRAGMENT_PATH
    ]

    assert len(fragments) == 1
    assert fragments[0].methods == ("POST",)
    assert fragments[0].owner_fe_user_plugin == CORE_OWNER


def test_enabling_twice_registers_login_once(enabled_plugin):
    enabled_plugin.on_enable()

    rules = [page.rule for page in enabled_plugin.page_registry.pages()]
    assert rules.count("/login") == 1


def test_page_context_carries_the_raw_redirect_for_the_fragment():
    assert login_page_context(FakeThemeRequest({"redirect": "/shop"})) == {
        "redirect": "/shop"
    }
    assert login_page_context(FakeThemeRequest()) == {"redirect": ""}


def test_login_page_keeps_the_spa_testids_copy_and_no_flash_markers(enabled_plugin):
    html = _render(
        enabled_plugin, login.LOGIN_PAGE_TEMPLATE, {"redirect": "/pay/stripe?a=1&b=2"}
    )

    assert '<meta name="vbwd-frontend" content="theme">' in html
    assert re.search(
        r'<input[^>]*id="email"[^>]*type="email"[^>]*data-testid="email"', html
    )
    assert re.search(
        r'<input[^>]*id="password"[^>]*type="password"[^>]*data-testid="password"', html
    )
    assert re.search(r'<button[^>]*type="submit"[^>]*data-testid="login-button"', html)
    assert ">Login</h1>" in html
    assert ">Email</label>" in html and ">Password</label>" in html
    assert ">Login</button>" in html
    assert f'hx-post="{LOGIN_FRAGMENT_PATH}"' in html
    assert 'value="/pay/stripe?a=1&amp;b=2"' in html
    assert 'data-auth="pending"' in html and "data-vbwd-guest-only" in html
    assert 'data-testid="error-message"' not in html


def test_result_partial_renders_the_spa_error_message(enabled_plugin):
    html = _render(
        enabled_plugin,
        login.LOGIN_RESULT_TEMPLATE,
        {"session": None, "error_message": "Invalid credentials"},
    )

    assert re.search(
        r'<div class="error" data-testid="error-message">\s*Invalid credentials\s*</div>',
        html,
    )
    assert "data-vbwd-session" not in html


def test_result_partial_carries_the_session_directive_as_safe_json(enabled_plugin):
    session = {
        "token": "a.b.c",
        "user_id": "u-1",
        "user_permissions": ["shop.*"],
        "redirect": "</script><b>",
    }

    html = _render(
        enabled_plugin,
        login.LOGIN_RESULT_TEMPLATE,
        {"session": session, "error_message": None},
    )

    match = re.search(
        r'<script type="application/json" data-vbwd-session>(.*?)</script>', html
    )
    assert match and json.loads(match.group(1)) == session
    assert "</script><b>" not in match.group(1)
    assert 'data-testid="error-message"' not in html


def _answer(monkeypatch, answer):
    calls = []

    def fake_call_api(theme_request, method, path, **options):
        calls.append((method, path, options))
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(login, "call_api", fake_call_api)
    return calls


def test_successful_login_writes_the_spa_session_keys(monkeypatch):
    calls = _answer(
        monkeypatch,
        {
            "success": True,
            "token": "a.b.c",
            "user_id": "u-1",
            "user": {"user_permissions": ["*"]},
        },
    )
    theme_request = FakeThemeRequest(
        {"email": "test@example.com", "password": "pw", "redirect": "/shop"}
    )

    context = login_result_context(theme_request)

    assert calls == [
        (
            "POST",
            LOGIN_API_PATH,
            {"json": {"email": "test@example.com", "password": "pw"}},
        )
    ]
    assert context == {
        "session": {
            "token": "a.b.c",
            "user_id": "u-1",
            "user_permissions": ["*"],
            "redirect": "/shop",
        },
        "error_message": None,
    }


def test_login_without_permissions_stores_an_empty_list_and_no_redirect(monkeypatch):
    _answer(monkeypatch, {"success": True, "token": "t", "user_id": "u-1"})

    context = login_result_context(FakeThemeRequest({"email": "a", "password": "b"}))

    assert context["session"]["user_permissions"] == []
    assert context["session"]["redirect"] is None


def test_refused_login_shows_the_api_error(monkeypatch):
    _answer(monkeypatch, ThemeApiError(401, "Invalid credentials"))

    context = login_result_context(FakeThemeRequest({"email": "a", "password": "b"}))

    assert context == {"session": None, "error_message": "Invalid credentials"}


def test_unsuccessful_body_without_message_leaves_the_translated_default(
    monkeypatch, enabled_plugin
):
    _answer(monkeypatch, {"success": False})

    context = login_result_context(FakeThemeRequest({"email": "a", "password": "b"}))
    html = _render(enabled_plugin, login.LOGIN_RESULT_TEMPLATE, context)

    assert context == {"session": None, "error_message": None}
    assert re.search(r'data-testid="error-message">\s*Login failed\s*</div>', html)


def test_login_translations_equal_the_spa_copy(enabled_plugin):
    html = _render(enabled_plugin, login.LOGIN_PAGE_TEMPLATE, {"redirect": ""})

    assert "login.title" not in html and "login.emailLabel" not in html


def test_login_catalog_equals_the_spa_login_copy():
    from pathlib import Path

    spa_catalog = (
        Path(__file__).resolve().parents[4].parent
        / "vbwd-fe-user"
        / "vue"
        / "src"
        / "i18n"
        / "locales"
        / "en.json"
    )
    theme_catalog = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "theme"
            / "themes"
            / "basic"
            / "translations"
            / "en.json"
        ).read_text(encoding="utf-8")
    )
    if not spa_catalog.is_file():
        pytest.skip("fe-user is not next to vbwd-backend (plugin CI)")
    spa_login = json.loads(spa_catalog.read_text(encoding="utf-8"))["login"]

    for key, value in theme_catalog.items():
        path = key.split(".")[1:]
        expected = spa_login
        for part in path:
            expected = expected[part]
        assert value == expected, key


def test_translated_login_catalogs_equal_the_spa_login_copy():
    from pathlib import Path

    from plugins.theme.tests.catalog_contract import translated_catalog_paths
    from plugins.theme.theme.theme_registry import (
        BASIC_THEME_DESCRIPTOR,
        TRANSLATIONS_DIRECTORY,
    )

    spa_locales = (
        Path(__file__).resolve().parents[4].parent
        / "vbwd-fe-user"
        / "vue"
        / "src"
        / "i18n"
        / "locales"
    )
    if not spa_locales.is_dir():
        pytest.skip("fe-user is not next to vbwd-backend (plugin CI)")
    translations = BASIC_THEME_DESCRIPTOR.root / TRANSLATIONS_DIRECTORY
    for catalog_path in translated_catalog_paths(translations):
        spa_catalog = spa_locales / catalog_path.name
        spa_messages = json.loads(spa_catalog.read_text(encoding="utf-8"))
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        for key, value in catalog.items():
            expected = spa_messages
            for part in key.split("."):
                expected = expected[part]
            assert value == expected, (catalog_path.stem, key)
