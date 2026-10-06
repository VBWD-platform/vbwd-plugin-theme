"""Which languages a themed page may render in (S152-05 / D13): the language-policy port.

D13 says the CMS defines language. ``theme`` stays cms-agnostic: it depends on
:class:`ThemeLanguagePolicy` only, and ``theme_cms`` registers the cms policy
through ``ThemePlugin.set_language_policy`` from its ``on_enable``. Until then
:class:`CoreLanguagePolicy` answers from core ``GET /api/v1/config/languages``.
"""
from typing import Protocol, Tuple

from flask import g

from .theme_api import call_api
from .theme_request import ThemeRequest

CORE_LANGUAGES_PATH = "/api/v1/config/languages"
CORE_LANGUAGES_CACHE_KEY = "theme_core_languages"


class ThemeLanguagePolicy(Protocol):
    """The enabled languages and the default one, for the request being rendered."""

    def enabled_languages(self, theme_request: ThemeRequest) -> Tuple[str, ...]:
        """Language codes a page may render in."""

    def default_language(self, theme_request: ThemeRequest) -> str:
        """The language used when nothing else applies."""


class CoreLanguagePolicy:
    """Core's language list (``{languages: [{code, name}], default}``), read once per request."""

    def enabled_languages(self, theme_request: ThemeRequest) -> Tuple[str, ...]:
        enabled_languages, _default_language = self._core_languages(theme_request)
        return enabled_languages

    def default_language(self, theme_request: ThemeRequest) -> str:
        _enabled_languages, default_language = self._core_languages(theme_request)
        return default_language

    @staticmethod
    def _core_languages(theme_request: ThemeRequest) -> Tuple[Tuple[str, ...], str]:
        # ``g`` lives as long as the outer request; inner C2 calls get their own.
        if CORE_LANGUAGES_CACHE_KEY not in g:
            body = call_api(theme_request, "GET", CORE_LANGUAGES_PATH)
            enabled_languages = tuple(
                language["code"] for language in body["languages"]
            )
            g.setdefault(CORE_LANGUAGES_CACHE_KEY, (enabled_languages, body["default"]))
        cached_languages: Tuple[Tuple[str, ...], str] = g.get(CORE_LANGUAGES_CACHE_KEY)
        return cached_languages
