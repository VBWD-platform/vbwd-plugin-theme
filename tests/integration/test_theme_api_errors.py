"""S152-04 — ``test_api_error_maps_to_themed_error_fragment`` on a real ``create_app``.

A fake page's ``build_context`` calls a test-only inner ``/api/v1`` route
through ``call_api`` (core C2). A non-2xx answer raises ``ThemeApiError``, which
the page wrapper maps to the themed error page: 404 → 404, 403 → 403, else 500.
Only the themed 404 carries the ``X-VBWD-Not-Found: 1`` label: nginx answers a
real 404 for it instead of falling back to the SPA shell (soft-404).
"""
import pytest

from plugins.theme.tests.integration.fake_adapter import build_fake_api_blueprint
from plugins.theme.theme.page_rendering import (
    NOT_FOUND_LABEL_HEADER,
    NOT_FOUND_LABEL_HEADER_VALUE,
)

RENDER_HEADER = {"X-VBWD-Render": "1"}


@pytest.fixture
def client(make_client):
    theme_client, _app = make_client(
        "theme", api_blueprints=[build_fake_api_blueprint()]
    )
    return theme_client


def test_a_2xx_inner_answer_feeds_the_page_context(client):
    response = client.get("/fake-api-status/200", headers=RENDER_HEADER)

    assert response.status_code == 200
    assert "answer=42" in response.get_data(as_text=True)


@pytest.mark.parametrize(
    "inner_status, page_status, error_testid",
    [
        (404, 404, "error-404"),
        (403, 403, "error-403"),
        (500, 500, "error-500"),
        (401, 500, "error-500"),
        (429, 500, "error-500"),
    ],
)
def test_api_error_maps_to_themed_error_fragment(
    client, inner_status, page_status, error_testid
):
    response = client.get(f"/fake-api-status/{inner_status}", headers=RENDER_HEADER)

    html = response.get_data(as_text=True)
    assert response.status_code == page_status
    assert response.mimetype == "text/html"
    assert f'data-testid="{error_testid}"' in html
    assert '<meta name="vbwd-frontend" content="theme">' in html
    assert "answer=42" not in html


@pytest.mark.parametrize(
    "inner_status, is_labelled",
    [(404, True), (403, False), (500, False), (401, False)],
)
def test_only_the_themed_404_carries_the_not_found_label(
    client, inner_status, is_labelled
):
    response = client.get(f"/fake-api-status/{inner_status}", headers=RENDER_HEADER)

    label = response.headers.get(NOT_FOUND_LABEL_HEADER)
    assert (label == NOT_FOUND_LABEL_HEADER_VALUE) is is_labelled
    assert is_labelled or label is None


def test_the_not_found_label_is_x_vbwd_not_found_1():
    """The nginx contract (vbwd-fe-user ``frontend-router.conf``): name and value."""
    assert (NOT_FOUND_LABEL_HEADER, NOT_FOUND_LABEL_HEADER_VALUE) == (
        "X-VBWD-Not-Found",
        "1",
    )


def test_an_unmarked_request_404s_without_the_label_so_nginx_serves_the_spa(client):
    response = client.get("/fake-api-status/200")

    assert response.status_code == 404
    assert NOT_FOUND_LABEL_HEADER not in response.headers
