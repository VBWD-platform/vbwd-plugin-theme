"""S152-04 — ``test_api_error_maps_to_themed_error_fragment`` on a real ``create_app``.

A fake page's ``build_context`` calls a test-only inner ``/api/v1`` route
through ``call_api`` (core C2). A non-2xx answer raises ``ThemeApiError``, which
the page wrapper maps to the themed error page: 404 → 404, 403 → 403, else 500.
"""
import pytest

from plugins.theme.tests.integration.fake_adapter import build_fake_api_blueprint

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
