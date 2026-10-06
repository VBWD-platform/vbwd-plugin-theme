"""S152-06b — theme fragments (htmx islands) on a real ``create_app``.

A fragment answers WITHOUT the ``X-VBWD-Render`` page marker (nginx proxies
``/_render/*`` as-is), renders only its partial (no document shell) with the
request's language, is never cached, receives query arguments (GET) and form
fields (POST), keeps its owner's fe-user toggle, is absent in vue mode, and maps
an inner API failure to a bare status (404 / 403 / 500).
"""
import pytest

from plugins.theme.tests.integration.fake_adapter import (
    FAKE_ECHO_FRAGMENT_PATH,
    FAKE_FORM_FRAGMENT_PATH,
    FAKE_REDIRECT_FRAGMENT_PATH,
    build_fake_api_blueprint,
)
from vbwd.security.route_audit import find_unprotected_routes


@pytest.fixture
def theme_app(make_client):
    return make_client("theme", api_blueprints=[build_fake_api_blueprint()])


def test_a_get_fragment_answers_without_the_page_marker_as_a_bare_partial(theme_app):
    client, _app = theme_app

    response = client.get(FAKE_ECHO_FRAGMENT_PATH, query_string={"q": "<b>x</b>"})

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert response.headers["Cache-Control"] == "no-store"
    assert html.strip() == (
        '<p data-testid="fake-fragment" lang="en">Hello q=&lt;b&gt;x&lt;/b&gt;</p>'
    )
    assert "<html" not in html


def test_a_fragment_renders_in_the_request_language(theme_app):
    client, _app = theme_app
    client.set_cookie("vbwd_lang", "de")

    html = client.get(FAKE_ECHO_FRAGMENT_PATH).get_data(as_text=True)

    assert 'lang="de"' in html


def test_a_post_fragment_receives_the_form_fields(theme_app):
    client, _app = theme_app

    response = client.post(FAKE_FORM_FRAGMENT_PATH, data={"name": "Ada"})

    assert response.status_code == 200
    assert "q=Ada" in response.get_data(as_text=True)


def test_a_fragment_answers_only_its_declared_methods(theme_app):
    client, _app = theme_app

    assert client.post(FAKE_ECHO_FRAGMENT_PATH).status_code == 405
    assert client.get(FAKE_FORM_FRAGMENT_PATH).status_code == 405


@pytest.mark.parametrize(
    "inner_status, fragment_status",
    [(404, 404), (403, 403), (500, 500), (429, 500), (401, 401)],
)
def test_an_inner_api_error_is_a_bare_status(theme_app, inner_status, fragment_status):
    client, _app = theme_app

    response = client.get(f"/_render/_fragment/fake/status/{inner_status}")

    assert response.status_code == fragment_status
    assert response.get_data(as_text=True) == ""
    assert response.headers["Cache-Control"] == "no-store"


def test_a_fragment_404s_when_its_fe_user_plugin_is_disabled(make_client):
    client, _app = make_client("theme", owner_enabled=False)

    assert client.get(FAKE_ECHO_FRAGMENT_PATH).status_code == 404


def test_vue_mode_mounts_no_fragment(make_client):
    client, app = make_client("vue")

    assert client.get(FAKE_ECHO_FRAGMENT_PATH).status_code == 404
    assert FAKE_ECHO_FRAGMENT_PATH not in {
        str(rule) for rule in app.url_map.iter_rules()
    }


def test_fragments_pass_the_route_exposure_audit(theme_app):
    _client, app = theme_app

    offenders = [
        str(route.path)
        for route in find_unprotected_routes(app)
        if "/_render/_fragment/fake" in str(route.path)
    ]

    assert offenders == []


@pytest.mark.parametrize(
    "location", ["/checkout/confirmation?invoice_id=1", "https://pay.example/s/1"]
)
def test_a_fragment_redirect_answers_hx_redirect_with_an_empty_body(
    theme_app, location
):
    """S152-07 — a fragment ends an htmx flow by navigating (htmx reads HX-Redirect)."""
    client, _app = theme_app

    response = client.post(FAKE_REDIRECT_FRAGMENT_PATH, data={"to": location})

    assert response.status_code == 200
    assert response.headers["HX-Redirect"] == location
    assert response.get_data(as_text=True) == ""
    assert response.headers["Cache-Control"] == "no-store"
