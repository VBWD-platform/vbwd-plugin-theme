"""S152-04 — the page contract: the theme renders an adapter's template with its context.

An adapter page declares ``template`` + ``build_context``; the theme's route
wrapper builds a frozen :class:`ThemeRequest` and renders. Page navigations are
always anonymous (D4), even when a bearer header is present.
"""
import dataclasses

import pytest

from plugins.theme.tests.integration.fake_adapter import received_theme_requests
from plugins.theme.theme.viewer import ANONYMOUS_VIEWER

RENDER_HEADER = {"X-VBWD-Render": "1"}
ECHO_URL = "/fake-items/mug?colour=red"


def test_page_renders_its_template_with_the_built_context(make_client):
    client, _app = make_client("theme")

    response = client.get(ECHO_URL, headers=RENDER_HEADER)

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert '<meta name="vbwd-frontend" content="theme">' in html
    for expected in (
        "path=/fake-items/mug",
        "item=mug",
        "colour=red",
        "viewer=anonymous",
        "lang=en",
    ):
        assert expected in html


def test_build_context_receives_a_frozen_theme_request(make_client):
    client, _app = make_client("theme")

    client.get(ECHO_URL, headers=RENDER_HEADER)

    (theme_request,) = received_theme_requests
    assert theme_request.path == "/fake-items/mug"
    assert dict(theme_request.view_args) == {"item_slug": "mug"}
    assert theme_request.query_args.get("colour") == "red"
    assert theme_request.viewer is ANONYMOUS_VIEWER
    assert theme_request.language == "en"
    with pytest.raises(dataclasses.FrozenInstanceError):
        theme_request.path = "/elsewhere"


def test_page_render_is_anonymous_even_with_a_bearer_header(make_client):
    client, _app = make_client("theme")

    response = client.get(
        ECHO_URL,
        headers={**RENDER_HEADER, "Authorization": "Bearer some.jwt.token"},
    )

    assert response.status_code == 200
    assert "viewer=anonymous" in response.get_data(as_text=True)
    assert received_theme_requests[0].viewer is ANONYMOUS_VIEWER
