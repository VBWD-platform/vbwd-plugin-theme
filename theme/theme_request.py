"""The frozen request an adapter page's ``build_context`` receives (S152-04)."""
from dataclasses import dataclass, field
from typing import Any, Mapping

from flask import Request

from .viewer import Viewer

# The language before resolution, and the last translation fallback (D13).
FALLBACK_LANGUAGE = "en"


@dataclass(frozen=True)
class ThemeRequest:
    """What a page render is for: the public path, its arguments and the viewer.

    ``http_request`` is the incoming Flask request; inner API calls forward
    its allow-listed headers through it (``call_api``). It is excluded from
    equality and repr because it is transport, not page identity.
    ``language`` is the pre-context language (``ThemeLanguageResolver``); a
    page may still override it with the ``page_language`` context key.
    """

    path: str
    view_args: Mapping[str, Any]
    query_args: Mapping[str, Any]
    viewer: Viewer
    http_request: Request = field(compare=False, repr=False)
    language: str = FALLBACK_LANGUAGE
