"""Render one adapter page for one :class:`ThemeRequest` (S152-04)."""
from typing import Any, Dict

from flask import Response

from .language_resolver import PAGE_LANGUAGE_CONTEXT_KEY, ThemeLanguageResolver
from .page_registry import ThemePage
from .renderer import ThemeRenderer
from .theme_api import ThemeApiError, themed_error_status
from .theme_request import ThemeRequest

HTML_MIMETYPE = "text/html"
ERROR_TEMPLATE = "_shared/errors/{status}.html.j2"


def render_page(
    page: ThemePage,
    theme_request: ThemeRequest,
    renderer: ThemeRenderer,
    language_resolver: ThemeLanguageResolver,
) -> Response:
    """The page's template rendered with its ``build_context`` for the request's viewer.

    An inner API failure (``ThemeApiError``) becomes the themed 404 / 403 / 500 page.
    """
    try:
        context = build_page_context(page, theme_request, language_resolver)
    except ThemeApiError as api_error:
        return _render_error_page(api_error, theme_request, renderer, language_resolver)
    html = renderer.render(page.template, context, viewer=theme_request.viewer)
    return Response(html, mimetype=HTML_MIMETYPE)


def build_page_context(
    page: ThemePage,
    theme_request: ThemeRequest,
    language_resolver: ThemeLanguageResolver,
) -> Dict[str, Any]:
    """The adapter's context plus the document languages (D13).

    The adapter may return ``page_language`` (e.g. the CMS post's language); it
    is consumed here and becomes the final ``language`` when enabled.
    """
    context = dict(page.build_context(theme_request))
    page_language = context.pop(PAGE_LANGUAGE_CONTEXT_KEY, None)
    context.update(language_resolver.document_languages(theme_request, page_language))
    return context


def _render_error_page(
    api_error: ThemeApiError,
    theme_request: ThemeRequest,
    renderer: ThemeRenderer,
    language_resolver: ThemeLanguageResolver,
) -> Response:
    status = themed_error_status(api_error.status)
    html = renderer.render(
        ERROR_TEMPLATE.format(status=status),
        language_resolver.document_languages(theme_request),
        viewer=theme_request.viewer,
    )
    return Response(html, status=status, mimetype=HTML_MIMETYPE)
