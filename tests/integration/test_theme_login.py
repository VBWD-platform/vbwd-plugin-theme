"""S152-07 A — themed ``/login`` on a real ``create_app`` against the real auth API.

The page belongs to fe-user core (owner ``core``): it answers with the render
marker even when no fe-user plugin is enabled. The fragment dispatches to the
real ``POST /api/v1/auth/login`` (core C2), so the brute-force limit and the
credential check are the API's own. Users come from the core test-data seeder
inside a rolled-back transaction.
"""
import json
import os
import re

import pytest

from plugins.theme.tests.e2e_spec_contract import spec_selector_drift

RENDER_HEADER = {"X-VBWD-Render": "1"}
LOGIN_FRAGMENT_PATH = "/_render/_fragment/login"
TEST_USER = {"email": "test@example.com", "password": "TestPass123@"}


@pytest.fixture
def seeded_client(make_client):
    from vbwd.extensions import db as database
    from vbwd.testing.integration_db import (
        ensure_schema_and_baseline,
        rollback_isolation,
    )
    from vbwd.testing.test_data_seeder import TestDataSeeder

    client, app = make_client("theme", owner_enabled=False)
    with app.app_context():
        ensure_schema_and_baseline(database)
        with rollback_isolation(database):
            previous_seed_flag = os.environ.get("TEST_DATA_SEED")
            os.environ["TEST_DATA_SEED"] = "true"
            try:
                TestDataSeeder(database.session).seed()
            finally:
                if previous_seed_flag is None:
                    os.environ.pop("TEST_DATA_SEED", None)
                else:
                    os.environ["TEST_DATA_SEED"] = previous_seed_flag
            yield client


def _session_directive(html):
    match = re.search(
        r'<script type="application/json" data-vbwd-session>(.*?)</script>', html
    )
    return json.loads(match.group(1)) if match else None


def test_login_page_answers_for_the_core_owner_with_no_fe_user_plugin_enabled(
    make_client,
):
    client, _app = make_client("theme", owner_enabled=False)

    response = client.get("/login?redirect=/shop", headers=RENDER_HEADER)

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'data-testid="login-button"' in html
    assert 'name="redirect" value="/shop"' in html


def test_login_page_without_the_render_marker_falls_back_to_the_spa(make_client):
    client, _app = make_client("theme", owner_enabled=False)

    assert client.get("/login").status_code == 404


def test_vue_mode_has_no_themed_login(make_client):
    client, _app = make_client("vue", owner_enabled=False)

    assert client.get("/login", headers=RENDER_HEADER).status_code == 404
    assert client.post(LOGIN_FRAGMENT_PATH, data=TEST_USER).status_code == 404


def test_valid_credentials_answer_the_session_directive_with_the_spa_keys(
    seeded_client,
):
    response = seeded_client.post(
        LOGIN_FRAGMENT_PATH, data={**TEST_USER, "redirect": "/shop/cart"}
    )

    session = _session_directive(response.get_data(as_text=True))
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert session is not None
    assert session["token"].count(".") == 2
    assert session["user_id"]
    assert isinstance(session["user_permissions"], list)
    assert session["redirect"] == "/shop/cart"
    profile = seeded_client.get(
        "/api/v1/user/profile",
        headers={"Authorization": f"Bearer {session['token']}"},
    )
    assert profile.status_code == 200
    assert str(profile.get_json()["user"]["id"]) == session["user_id"]


def test_an_off_site_redirect_becomes_the_dashboard(seeded_client):
    response = seeded_client.post(
        LOGIN_FRAGMENT_PATH, data={**TEST_USER, "redirect": "https://evil.example"}
    )

    assert _session_directive(response.get_data(as_text=True))["redirect"] == (
        "/dashboard"
    )


def test_wrong_password_renders_the_spa_error_message(seeded_client):
    response = seeded_client.post(
        LOGIN_FRAGMENT_PATH,
        data={"email": TEST_USER["email"], "password": "wrongpassword"},
    )

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'data-testid="error-message"' in html
    assert _session_directive(html) is None


AUTH_SPEC = "vue/tests/e2e/auth.spec.ts"
FIXTURES = "vue/tests/e2e/fixtures/checkout.fixtures.ts"
LOGIN_CONTRACT = [
    ("email", AUTH_SPEC, 11, "page"),
    ("password", AUTH_SPEC, 12, "page"),
    ("login-button", AUTH_SPEC, 13, "page"),
    ("error-message", AUTH_SPEC, 24, "refused"),
    ("email", FIXTURES, 10, "page"),
    ("password", FIXTURES, 11, "page"),
    ("login-button", FIXTURES, 12, "page"),
]


def test_login_e2e_dom_contract(seeded_client):
    """S152-07 — auth.spec / loginAsTestUser selectors exist on the themed /login."""
    outputs = {
        "page": seeded_client.get("/login", headers=RENDER_HEADER).get_data(
            as_text=True
        ),
        "refused": seeded_client.post(
            LOGIN_FRAGMENT_PATH,
            data={"email": TEST_USER["email"], "password": "wrongpassword"},
        ).get_data(as_text=True),
    }

    missing = [
        f"{spec}:{line} {testid}"
        for testid, spec, line, output in LOGIN_CONTRACT
        if f'data-testid="{testid}"' not in outputs[output]
    ]

    assert not missing, missing


def test_login_contract_lines_still_use_these_selectors():
    from pathlib import Path

    fe_user = Path(__file__).resolve().parents[4].parent / "vbwd-fe-user"
    if not (fe_user / AUTH_SPEC).is_file():
        pytest.skip("fe-user is not next to vbwd-backend (plugin CI)")
    pins = [
        (f'data-testid="{testid}"', spec, line)
        for testid, spec, line, _output in LOGIN_CONTRACT
    ]

    assert spec_selector_drift(fe_user, pins) == []
