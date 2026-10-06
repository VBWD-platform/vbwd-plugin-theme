"""Serve one registered :class:`ThemeFragment` (S152-06b).

The fragment renders only its partial, in the request's language, for the
anonymous viewer (personalisation stays with ``/regions``). It is never
cached. An inner API failure is a bare status — htmx swaps nothing on an error;
an inner 401 stays 401 so the runtime ends the session (D4). A
``ThemeFragmentRedirect`` answers ``HX-Redirect`` with an empty body.
"""
from types import MappingProxyType
from typing import Callable

from flask import Response, abort, request

from .fe_user_manifest import FeUserPluginManifest
from .fragment_registry import ThemeFragment, ThemeFragmentRedirect
from .language_resolver import ThemeLanguageResolver
from .renderer import ThemeRenderer
from .theme_api import ThemeApiError, themed_error_status
from .theme_request import ThemeRequest
from .viewer import ANONYMOUS_VIEWER

HTML_MIMETYPE = "text/html"
NO_STORE = "no-store"
NOT_FOUND = 404
UNAUTHORIZED = 401
HX_REDIRECT_HEADER = "HX-Redirect"


def _no_store(response: Response) -> Response:
    response.headers["Cache-Control"] = NO_STORE
    return response


def _bare_error_status(api_status: int) -> int:
    """401 stays 401 (the runtime ends the session); else the themed error status."""
    return (
        UNAUTHORIZED if api_status == UNAUTHORIZED else themed_error_status(api_status)
    )


def _redirect(location: str) -> Response:
    response = Response("", mimetype=HTML_MIMETYPE)
    response.headers[HX_REDIRECT_HEADER] = location
    return _no_store(response)


def build_fragment_view(
    fragment: ThemeFragment,
    manifest: FeUserPluginManifest,
    renderer: ThemeRenderer,
    language_resolver: ThemeLanguageResolver,
) -> Callable:
    def view(**view_args):
        if not manifest.is_enabled(fragment.owner_fe_user_plugin):
            abort(NOT_FOUND)
        theme_request = language_resolver.with_pre_context_language(
            ThemeRequest(
                path=request.path,
                view_args=MappingProxyType(dict(view_args)),
                query_args=request.values,
                viewer=ANONYMOUS_VIEWER,
                http_request=request,
            )
        )
        try:
            context = dict(fragment.build_context(theme_request))
        except ThemeFragmentRedirect as redirect:
            return _redirect(redirect.location)
        except ThemeApiError as api_error:
            return _no_store(Response("", status=_bare_error_status(api_error.status)))
        context.update(language_resolver.document_languages(theme_request))
        html = renderer.render(fragment.template, context, viewer=theme_request.viewer)
        return _no_store(Response(html, mimetype=HTML_MIMETYPE))

    view.__name__ = fragment.endpoint
    return view
