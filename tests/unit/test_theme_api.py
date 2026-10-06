"""S152-04 / D3 — ``call_api``: adapters read the public API through core C2."""
from types import MappingProxyType

import pytest
from flask import Flask, request
from werkzeug.datastructures import Headers, ImmutableMultiDict

from plugins.theme.theme.theme_api import ThemeApiError, call_api, themed_error_status
from plugins.theme.theme.theme_request import ThemeRequest
from plugins.theme.theme.viewer import ANONYMOUS_VIEWER
from vbwd.services.internal_api import InternalResponse


class FakeInternalApiClient:
    """Honours the ``InternalApiClient.request`` contract; records each call."""

    def __init__(self, status: int, text: str) -> None:
        self._status = status
        self._text = text
        self.calls: list = []

    def request(self, method, path, **options) -> InternalResponse:
        self.calls.append((method, path, options))
        return InternalResponse(status=self._status, headers=Headers(), text=self._text)


def _app_with(fake_client: FakeInternalApiClient) -> Flask:
    app = Flask(__name__)
    app.extensions["internal_api"] = fake_client
    return app


def _theme_request(http_request) -> ThemeRequest:
    return ThemeRequest(
        path="/shop",
        view_args=MappingProxyType({}),
        query_args=ImmutableMultiDict(),
        viewer=ANONYMOUS_VIEWER,
        http_request=http_request,
    )


def test_returns_the_json_body_and_forwards_the_incoming_request():
    fake_client = FakeInternalApiClient(200, '{"items": [1, 2]}')
    app = _app_with(fake_client)

    with app.test_request_context("/shop"):
        http_request = request._get_current_object()
        body = call_api(
            _theme_request(http_request),
            "GET",
            "/api/v1/shop/products",
            query={"page": 2},
        )

    assert body == {"items": [1, 2]}
    (method, path, options) = fake_client.calls[0]
    assert (method, path) == ("GET", "/api/v1/shop/products")
    assert options["forward_from"] is http_request
    assert options["query"] == {"page": 2}


@pytest.mark.parametrize(
    "status, text, expected_message",
    [
        (404, '{"error": "Product not found"}', "Product not found"),
        (429, "Too Many Requests", "Too Many Requests"),
        (500, "", ""),
    ],
)
def test_non_2xx_raises_theme_api_error_with_status_and_message(
    status, text, expected_message
):
    app = _app_with(FakeInternalApiClient(status, text))

    with app.test_request_context("/shop"):
        with pytest.raises(ThemeApiError) as raised:
            call_api(_theme_request(request), "GET", "/api/v1/shop/products/x")

    assert raised.value.status == status
    assert raised.value.message == expected_message


@pytest.mark.parametrize(
    "api_status, page_status",
    [(404, 404), (403, 403), (401, 500), (429, 500), (400, 500), (502, 500)],
)
def test_themed_error_status_maps_to_404_403_or_500(api_status, page_status):
    assert themed_error_status(api_status) == page_status
