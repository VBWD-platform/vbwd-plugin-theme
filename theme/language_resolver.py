"""The language a themed page renders in (S152-05 / D13).

Before the page context is built: the ``vbwd_lang`` cookie, else the best
``Accept-Language`` entry (quality-ordered, matched on the primary subtag, so
``de-AT`` → ``de``), else the policy default — the cookie and the header count
only when the language is enabled. ``ThemeRequest.language`` carries that
value into ``build_context``. A page (e.g. a CMS post) may then return the
reserved context key ``page_language``; it wins when enabled. The final
language is what ``<html lang>`` and the translations use.
"""
from dataclasses import replace
from typing import Dict, Iterator, Optional

from .language_policy import ThemeLanguagePolicy
from .theme_request import ThemeRequest

LANGUAGE_COOKIE_NAME = "vbwd_lang"
PAGE_LANGUAGE_CONTEXT_KEY = "page_language"
LANGUAGE_CONTEXT_KEY = "language"
DEFAULT_LANGUAGE_CONTEXT_KEY = "default_language"
ANY_LANGUAGE = "*"
SUBTAG_SEPARATOR = "-"


class ThemeLanguageResolver:
    """Resolves the page language through the registered :class:`ThemeLanguagePolicy`."""

    def __init__(self, policy: ThemeLanguagePolicy) -> None:
        self._policy = policy

    @property
    def policy(self) -> ThemeLanguagePolicy:
        return self._policy

    def set_policy(self, policy: ThemeLanguagePolicy) -> None:
        """Replace the policy (last write wins); ``theme_cms`` registers the cms one."""
        self._policy = policy

    def pre_context_language(self, theme_request: ThemeRequest) -> str:
        enabled_languages = self._policy.enabled_languages(theme_request)
        for candidate in self._requested_languages(theme_request):
            if candidate in enabled_languages:
                return candidate
        return self._policy.default_language(theme_request)

    def with_pre_context_language(self, theme_request: ThemeRequest) -> ThemeRequest:
        """``theme_request`` carrying the pre-context language for ``build_context``."""
        return replace(theme_request, language=self.pre_context_language(theme_request))

    def document_languages(
        self, theme_request: ThemeRequest, page_language: Optional[str] = None
    ) -> Dict[str, str]:
        """The final ``language`` and the policy ``default_language`` for the template."""
        enabled_languages = self._policy.enabled_languages(theme_request)
        final_language = (
            page_language
            if page_language in enabled_languages
            else theme_request.language
        )
        return {
            LANGUAGE_CONTEXT_KEY: final_language,
            DEFAULT_LANGUAGE_CONTEXT_KEY: self._policy.default_language(theme_request),
        }

    @staticmethod
    def _requested_languages(theme_request: ThemeRequest) -> Iterator[str]:
        http_request = theme_request.http_request
        cookie_language = http_request.cookies.get(LANGUAGE_COOKIE_NAME)
        if cookie_language:
            yield cookie_language
        # Werkzeug orders by quality but keeps q=0 entries and the ``*`` wildcard.
        for language_tag, quality in http_request.accept_languages:
            if quality > 0 and language_tag != ANY_LANGUAGE:
                yield language_tag.split(SUBTAG_SEPARATOR, 1)[0].lower()
