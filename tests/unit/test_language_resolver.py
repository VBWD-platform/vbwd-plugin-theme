"""S152-05 / D13 — ThemeLanguageResolver: cookie > Accept-Language > policy default.

The resolver only knows the :class:`ThemeLanguagePolicy` port; the fake below
honours the same contract as ``CoreLanguagePolicy`` (and the cms policy
``theme_cms`` will register), so a policy swap is behaviour-preserving.
"""
from types import MappingProxyType
from typing import Optional, Tuple

import pytest
from flask import Flask, request
from werkzeug.datastructures import ImmutableMultiDict

from plugins.theme.theme.language_resolver import (
    LANGUAGE_CONTEXT_KEY,
    DEFAULT_LANGUAGE_CONTEXT_KEY,
    ThemeLanguageResolver,
)
from plugins.theme.theme.theme_request import ThemeRequest
from plugins.theme.theme.viewer import ANONYMOUS_VIEWER

ENABLED_LANGUAGES = ("en", "de", "fr")


class FakeLanguagePolicy:
    """A ThemeLanguagePolicy with fixed answers; counts how often it is asked."""

    def __init__(
        self, enabled_languages: Tuple[str, ...] = ENABLED_LANGUAGES, default="en"
    ) -> None:
        self._enabled_languages = enabled_languages
        self._default_language = default
        self.questions = 0

    def enabled_languages(self, theme_request: ThemeRequest) -> Tuple[str, ...]:
        self.questions += 1
        return self._enabled_languages

    def default_language(self, theme_request: ThemeRequest) -> str:
        self.questions += 1
        return self._default_language


@pytest.fixture
def app() -> Flask:
    return Flask(__name__)


def _theme_request() -> ThemeRequest:
    return ThemeRequest(
        path="/page",
        view_args=MappingProxyType({}),
        query_args=ImmutableMultiDict(),
        viewer=ANONYMOUS_VIEWER,
        http_request=request._get_current_object(),
    )


def _pre_context_language(
    app: Flask,
    resolver: ThemeLanguageResolver,
    cookie: Optional[str] = None,
    accept_language: Optional[str] = None,
) -> str:
    headers = {}
    if cookie is not None:
        headers["Cookie"] = f"vbwd_lang={cookie}"
    if accept_language is not None:
        headers["Accept-Language"] = accept_language
    with app.test_request_context("/page", headers=headers):
        return resolver.pre_context_language(_theme_request())


def test_cookie_beats_accept_language(app):
    resolver = ThemeLanguageResolver(FakeLanguagePolicy())

    assert (
        _pre_context_language(app, resolver, cookie="fr", accept_language="de") == "fr"
    )


def test_accept_language_beats_the_default(app):
    resolver = ThemeLanguageResolver(FakeLanguagePolicy())

    assert _pre_context_language(app, resolver, accept_language="de") == "de"


def test_without_cookie_or_header_the_policy_default_wins(app):
    resolver = ThemeLanguageResolver(FakeLanguagePolicy(default="fr"))

    assert _pre_context_language(app, resolver) == "fr"


def test_a_cookie_outside_enabled_languages_is_ignored(app):
    resolver = ThemeLanguageResolver(FakeLanguagePolicy(default="de"))

    assert _pre_context_language(app, resolver, cookie="xx") == "de"


def test_a_disabled_cookie_falls_through_to_accept_language(app):
    resolver = ThemeLanguageResolver(FakeLanguagePolicy())

    assert (
        _pre_context_language(app, resolver, cookie="xx", accept_language="fr") == "fr"
    )


@pytest.mark.parametrize(
    "accept_language, expected",
    [
        ("fr;q=0.2, de;q=0.9", "de"),
        ("ja, fr;q=0.4, de;q=0.3", "fr"),
        ("de-AT", "de"),
        ("DE-at;q=0.8, en;q=0.1", "de"),
        ("*;q=0.9, fr;q=0.5", "fr"),
        ("de;q=0, fr;q=0.1", "fr"),
        ("de;q=0, ja", "en"),
        ("ja, zh", "en"),
        ("not a header;;", "en"),
    ],
)
def test_accept_language_is_quality_ordered_and_matches_the_primary_subtag(
    app, accept_language, expected
):
    resolver = ThemeLanguageResolver(FakeLanguagePolicy())

    assert _pre_context_language(app, resolver, accept_language=accept_language) == (
        expected
    )


def test_page_language_beats_the_cookie_when_enabled(app):
    resolver = ThemeLanguageResolver(FakeLanguagePolicy())

    with app.test_request_context("/page", headers={"Cookie": "vbwd_lang=fr"}):
        theme_request = resolver.with_pre_context_language(_theme_request())
        languages = resolver.document_languages(theme_request, page_language="de")

    assert theme_request.language == "fr"
    assert languages == {LANGUAGE_CONTEXT_KEY: "de", DEFAULT_LANGUAGE_CONTEXT_KEY: "en"}


def test_page_language_outside_enabled_languages_is_ignored(app):
    resolver = ThemeLanguageResolver(FakeLanguagePolicy())

    with app.test_request_context("/page", headers={"Cookie": "vbwd_lang=fr"}):
        theme_request = resolver.with_pre_context_language(_theme_request())
        languages = resolver.document_languages(theme_request, page_language="xx")

    assert languages[LANGUAGE_CONTEXT_KEY] == "fr"


def test_without_page_language_the_pre_context_language_is_final(app):
    resolver = ThemeLanguageResolver(FakeLanguagePolicy(default="de"))

    with app.test_request_context("/page"):
        theme_request = resolver.with_pre_context_language(_theme_request())
        languages = resolver.document_languages(theme_request)

    assert languages == {LANGUAGE_CONTEXT_KEY: "de", DEFAULT_LANGUAGE_CONTEXT_KEY: "de"}


def test_set_policy_replaces_the_policy_last_write_wins(app):
    resolver = ThemeLanguageResolver(FakeLanguagePolicy(default="en"))
    resolver.set_policy(FakeLanguagePolicy(default="fr"))
    replacement_policy = FakeLanguagePolicy(enabled_languages=("de",), default="de")
    resolver.set_policy(replacement_policy)

    assert _pre_context_language(app, resolver, cookie="fr") == "de"
    assert replacement_policy.questions > 0
