"""S152-05 — CoreLanguagePolicy: core ``GET /api/v1/config/languages`` via C2, once per request."""
from types import MappingProxyType

import pytest
from flask import Flask, request
from werkzeug.datastructures import Headers, ImmutableMultiDict

from plugins.theme.theme.language_policy import CORE_LANGUAGES_PATH, CoreLanguagePolicy
from plugins.theme.theme.theme_api import ThemeApiError
from plugins.theme.theme.theme_request import ThemeRequest
from plugins.theme.theme.viewer import ANONYMOUS_VIEWER
from vbwd.services.internal_api import InternalResponse

CORE_LANGUAGES_BODY = (
    '{"languages": [{"code": "en", "name": "English"},'
    ' {"code": "de", "name": "Deutsch"}], "default": "de"}'
)


class FakeInternalApiClient:
    """Honours the ``InternalApiClient.request`` contract; records each call."""

    def __init__(self, status: int = 200, text: str = CORE_LANGUAGES_BODY) -> None:
        self._status = status
        self._text = text
        self.calls: list = []

    def request(self, method, path, **options) -> InternalResponse:
        self.calls.append((method, path))
        return InternalResponse(status=self._status, headers=Headers(), text=self._text)


def _app_with(fake_client: FakeInternalApiClient) -> Flask:
    app = Flask(__name__)
    app.extensions["internal_api"] = fake_client
    return app


def _theme_request() -> ThemeRequest:
    return ThemeRequest(
        path="/page",
        view_args=MappingProxyType({}),
        query_args=ImmutableMultiDict(),
        viewer=ANONYMOUS_VIEWER,
        http_request=request._get_current_object(),
    )


def test_reads_enabled_and_default_languages_from_the_core_endpoint():
    fake_client = FakeInternalApiClient()
    policy = CoreLanguagePolicy()

    with _app_with(fake_client).test_request_context("/page"):
        theme_request = _theme_request()
        enabled_languages = policy.enabled_languages(theme_request)
        default_language = policy.default_language(theme_request)

    assert enabled_languages == ("en", "de")
    assert default_language == "de"
    assert fake_client.calls == [("GET", CORE_LANGUAGES_PATH)]


def test_the_core_answer_is_cached_per_request_only():
    fake_client = FakeInternalApiClient()
    policy = CoreLanguagePolicy()
    app = _app_with(fake_client)

    for _request_number in range(2):
        with app.test_request_context("/page"):
            policy.enabled_languages(_theme_request())
            policy.enabled_languages(_theme_request())
            policy.default_language(_theme_request())

    assert len(fake_client.calls) == 2


def test_a_failing_core_endpoint_is_not_silenced():
    policy = CoreLanguagePolicy()

    with _app_with(FakeInternalApiClient(status=500, text="{}")).test_request_context(
        "/page"
    ):
        with pytest.raises(ThemeApiError):
            policy.enabled_languages(_theme_request())
