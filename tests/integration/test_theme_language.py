"""S152-05 / D13 — page language on a real ``create_app``.

The default policy is ``CoreLanguagePolicy`` reading the REAL core
``GET /api/v1/config/languages`` through C2 (en, de, … with default ``en``).
The fake adapter's language page echoes the pre-context language, may return
``page_language`` (from ``?page_language=``) and calls a test API route that
echoes what an inner C2 call received.
"""
import pytest

from plugins.theme.tests.integration.fake_adapter import (
    FAKE_LANGUAGE_PAGE_PATH,
    build_fake_api_blueprint,
)

RENDER_HEADER = {"X-VBWD-Render": "1"}


class FixedLanguagePolicy:
    """A ThemeLanguagePolicy with fixed answers (same contract as CoreLanguagePolicy)."""

    def __init__(self, enabled_languages, default_language) -> None:
        self._enabled_languages = tuple(enabled_languages)
        self._default_language = default_language

    def enabled_languages(self, theme_request):
        return self._enabled_languages

    def default_language(self, theme_request):
        return self._default_language


@pytest.fixture
def theme_app(make_client):
    _client, app = make_client("theme", api_blueprints=[build_fake_api_blueprint()])
    return app


@pytest.fixture
def client(theme_app):
    return theme_app.test_client()


def _get_language_page(client, query="", cookie=None, accept_language=None):
    headers = dict(RENDER_HEADER)
    if accept_language is not None:
        headers["Accept-Language"] = accept_language
    if cookie is not None:
        client.set_cookie("vbwd_lang", cookie)
    response = client.get(f"{FAKE_LANGUAGE_PAGE_PATH}{query}", headers=headers)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_data(as_text=True)


def test_without_cookie_or_header_the_core_default_language_is_used(client):
    html = _get_language_page(client)

    assert '<html lang="en">' in html
    assert "pre=en" in html


def test_the_cookie_selects_a_core_enabled_language(client):
    html = _get_language_page(client, cookie="de", accept_language="fr")

    assert '<html lang="de">' in html
    assert "pre=de" in html


def test_a_cookie_core_does_not_enable_falls_back_to_the_core_default(client):
    html = _get_language_page(client, cookie="xx")

    assert '<html lang="en">' in html


def test_accept_language_primary_subtag_matches_a_core_language(client):
    html = _get_language_page(client, accept_language="xx, de-AT;q=0.8")

    assert '<html lang="de">' in html


def test_an_enabled_page_language_beats_the_cookie_and_sets_html_lang(client):
    html = _get_language_page(client, query="?page_language=fr", cookie="de")

    assert '<html lang="fr">' in html
    assert "pre=de" in html


def test_a_page_language_core_does_not_enable_is_ignored(client):
    html = _get_language_page(client, query="?page_language=xx", cookie="de")

    assert '<html lang="de">' in html


def test_ui_strings_come_from_the_contributed_catalog_of_the_final_language(client):
    assert "greeting=Hallo" in _get_language_page(client, cookie="de")
    assert "greeting=Bonjour" in _get_language_page(client, query="?page_language=fr")


def test_a_key_missing_in_the_final_language_falls_back_to_en(client):
    assert "farewell=Goodbye" in _get_language_page(client, cookie="de")


def test_an_inner_call_api_sees_the_same_cookie_and_accept_language(client):
    html = _get_language_page(client, cookie="de", accept_language="fr-CH;q=0.7")

    assert "inner-cookie=de" in html
    assert "inner-accept-language=fr-CH;q=0.7" in html


def test_a_registered_language_policy_replaces_the_core_one(theme_app, client):
    theme_plugin = theme_app.plugin_manager.get_plugin("theme")
    theme_plugin.set_language_policy(FixedLanguagePolicy(("it", "fr"), "it"))

    html = _get_language_page(client, cookie="de")

    assert '<html lang="it">' in html
    assert "pre=it" in html


def test_a_themed_error_page_carries_the_request_language(client):
    client.set_cookie("vbwd_lang", "de")

    response = client.get("/fake-api-status/404", headers=RENDER_HEADER)

    assert response.status_code == 404
    assert '<html lang="de">' in response.get_data(as_text=True)
