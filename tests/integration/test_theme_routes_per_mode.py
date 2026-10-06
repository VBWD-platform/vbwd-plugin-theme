"""S152-01 — the theme route table per frontend mode (W2), on a real ``create_app``.

Boot is narrowed to exactly the theme plugin plus a test-only fake adapter (no
real adapter, no domain plugin), so the route table is deterministic locally
and in an isolated CI clone. The fake adapter registers its page from
``on_enable`` — the same moment real adapters will — which proves the boot
ordering: the core enables every plugin before it mounts any blueprint.
"""
import pytest

from plugins.theme.tests.integration.fake_adapter import (
    FAKE_PAGE_PATH,
    FakeThemeAdapterPlugin,
)
from plugins.theme.theme.page_registry import ThemePageRegistrationError

RENDER_HEADER = {"X-VBWD-Render": "1"}
MODE_PROBE_PATH = "/_render/_theme/mode"
FAKE_PAGE_MARKER = '<p data-testid="fake-page">fake themed page</p>'


def test_vue_mode_mounts_no_page_route_even_with_the_render_header(make_client):
    client, app = make_client("vue")

    assert client.get(FAKE_PAGE_PATH, headers=RENDER_HEADER).status_code == 404
    assert FAKE_PAGE_PATH not in {str(rule) for rule in app.url_map.iter_rules()}


def test_vue_mode_has_no_mode_probe(make_client):
    client, _app = make_client("vue")

    assert client.get(MODE_PROBE_PATH).status_code == 404


def test_theme_mode_page_answers_only_with_the_render_header(make_client):
    client, _app = make_client("theme")

    themed = client.get(FAKE_PAGE_PATH, headers=RENDER_HEADER)
    assert themed.status_code == 200
    assert themed.get_data(as_text=True).strip() == FAKE_PAGE_MARKER
    assert client.get(FAKE_PAGE_PATH).status_code == 404
    assert client.get(FAKE_PAGE_PATH, headers={"X-VBWD-Render": "0"}).status_code == 404


def test_theme_mode_probe_reports_theme_without_any_header(make_client):
    client, _app = make_client("theme")

    response = client.get(MODE_PROBE_PATH)

    assert response.status_code == 200
    assert response.get_json() == {"mode": "theme"}


def test_theme_mode_page_404s_when_its_fe_user_plugin_is_disabled(make_client):
    client, _app = make_client("theme", owner_enabled=False)

    assert client.get(FAKE_PAGE_PATH, headers=RENDER_HEADER).status_code == 404


def test_theme_mode_page_404s_when_the_fe_user_manifest_is_missing(make_client):
    client, _app = make_client("theme", owner_enabled=None)

    assert client.get(FAKE_PAGE_PATH, headers=RENDER_HEADER).status_code == 404


def test_adapter_enabled_after_mount_fails_loudly(make_client):
    """A page registered once the blueprint is mounted would never be routed."""
    _client, app = make_client("theme")

    with app.app_context():
        with pytest.raises(
            ThemePageRegistrationError, match="after the theme blueprint"
        ):
            FakeThemeAdapterPlugin().on_enable()


STYLESHEET_PATH = "/_render/_theme/public/theme.css"
RUNTIME_SCRIPT_PATH = "/_render/_theme/static/basic/_shared/js/vbwd-theme.js"


def test_vue_mode_has_no_asset_routes(make_client):
    client, app = make_client("vue")

    assert client.get(STYLESHEET_PATH).status_code == 404
    assert client.get(RUNTIME_SCRIPT_PATH).status_code == 404
    assert not any(
        str(rule).startswith("/_render/_theme/") for rule in app.url_map.iter_rules()
    )


def test_theme_mode_serves_the_basic_stylesheet_and_runtime_without_a_header(
    make_client,
):
    client, _app = make_client("theme")

    stylesheet = client.get(STYLESHEET_PATH)
    assert stylesheet.status_code == 200
    assert stylesheet.mimetype == "text/css"
    assert '[data-auth="pending"] .vbwd-private-chrome' in stylesheet.get_data(
        as_text=True
    )
    assert stylesheet.headers["ETag"]

    runtime = client.get(RUNTIME_SCRIPT_PATH)
    assert runtime.status_code == 200
    assert b"window.VbwdTheme" in runtime.get_data()
