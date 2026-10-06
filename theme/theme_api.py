"""The one way adapters read and write domain data: the public API via core C2 (D3).

``call_api`` dispatches in-process to the SAME ``/api/v1/*`` endpoint the Vue
plugin calls, forwarding the incoming request's allow-listed headers
(``forward_from``), so RBAC, GDPR scoping and rate limits apply unchanged. A
non-2xx answer raises :class:`ThemeApiError`; the page wrapper turns it into a
themed error page.
"""
import json
from typing import Any

from vbwd.services.internal_api import resolve_internal_api_client

from .theme_request import ThemeRequest

HTTP_SUCCESS_RANGE = range(200, 300)
NOT_FOUND = 404
FORBIDDEN = 403
INTERNAL_SERVER_ERROR = 500
THEMED_ERROR_STATUSES = (NOT_FOUND, FORBIDDEN)


class ThemeApiError(Exception):
    """An inner API call answered with a non-2xx status."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"inner API answered {status}: {message}")
        self.status = status
        self.message = message


def call_api(
    theme_request: ThemeRequest, method: str, path: str, **options: Any
) -> Any:
    """The decoded JSON body of ``method path``; raises ThemeApiError on non-2xx."""
    response = resolve_internal_api_client().request(
        method, path, forward_from=theme_request.http_request, **options
    )
    if response.status not in HTTP_SUCCESS_RANGE:
        raise ThemeApiError(response.status, _error_message(response.text))
    return response.json()


def _error_message(response_text: str) -> str:
    """The API's ``{"error": …}`` message, else the raw body."""
    try:
        body = json.loads(response_text)
    except ValueError:
        return response_text
    if isinstance(body, dict) and isinstance(body.get("error"), str):
        return body["error"]
    return response_text


def themed_error_status(api_status: int) -> int:
    """The themed error page for an inner status: 404 → 404, 403 → 403, else 500."""
    return api_status if api_status in THEMED_ERROR_STATUSES else INTERNAL_SERVER_ERROR
