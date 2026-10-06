"""S152-04 / D12 — ``GET /_render/_fragment/regions`` on a real ``create_app``.

Real users are created through core services (``AuthService``,
``UserAccessLevelService``, a ``BaseRepository`` for the access level) and
removed afterwards. The viewer — including its access levels and permissions —
comes from the REAL ``GET /api/v1/user/profile`` via core C2.
"""
import re
import uuid

import pytest

from plugins.theme.tests.integration.fake_adapter import (
    FAKE_API_PREFIX,
    FAKE_LANGUAGE_PAGE_PATH,
    build_fake_api_blueprint,
    received_theme_requests,
)
from plugins.theme.theme import regions as regions_module

REGIONS_PATH = "/_render/_fragment/regions"
RENDER_HEADER = {"X-VBWD-Render": "1"}
GATED_URL = "/fake-gated/mug?colour=red"
PRO_LEVEL_SLUG = "theme-test-pro"
TEST_PASSWORD = "SecurePassword123!"
REGION_ID_PATTERN = re.compile(r'data-vbwd-region="([^"]+)"')


@pytest.fixture
def theme_app(make_client):
    _client, app = make_client("theme", api_blueprints=[build_fake_api_blueprint()])
    return app


@pytest.fixture
def client(theme_app):
    return theme_app.test_client()


@pytest.fixture
def create_user(theme_app):
    """Creates committed users through core services; deletes them afterwards."""
    from vbwd.extensions import db
    from vbwd.models.user_access_level import AccessLevel
    from vbwd.repositories.base import BaseRepository
    from vbwd.repositories.user_repository import UserRepository
    from vbwd.services.auth_service import AuthService
    from vbwd.services.user_access_level_service import UserAccessLevelService

    created_user_ids = []
    created_level_ids = []

    def create(access_level_slugs=()):
        with theme_app.app_context():
            user_repository = UserRepository(db.session)
            access_level_service = UserAccessLevelService(db.session)
            auth_service = AuthService(user_repository=user_repository)
            result = auth_service.register(
                f"theme-regions-{uuid.uuid4().hex}@example.com", TEST_PASSWORD
            )
            assert result.success, result.error
            created_user_ids.append(result.user_id)
            for slug in access_level_slugs:
                level = access_level_service.find_by_slug(slug)
                if level is None:
                    level = BaseRepository(db.session, AccessLevel).save(
                        AccessLevel(name=f"Theme test {slug}", slug=slug)
                    )
                    created_level_ids.append(level.id)
                access_level_service.assign(result.user_id, level.id)
            db.session.commit()
            token = auth_service.generate_access_token(
                result.user_id, user_repository.find_by_id(result.user_id).email
            )
            return str(result.user_id), {"Authorization": f"Bearer {token}"}

    yield create

    with theme_app.app_context():
        user_repository = UserRepository(db.session)
        access_level_service = UserAccessLevelService(db.session)
        for user_id in created_user_ids:
            for level in access_level_service.get_user_levels(user_id):
                access_level_service.revoke(user_id, level.id)
            db.session.commit()
            user_repository.delete(user_id)
            db.session.commit()
        level_repository = BaseRepository(db.session, AccessLevel)
        for level_id in created_level_ids:
            level_repository.delete(level_id)
        db.session.commit()


def _regions(client, path, headers, ids=None):
    query = {"path": path}
    if ids is not None:
        query["ids"] = ids
    return client.get(REGIONS_PATH, query_string=query, headers=headers)


def test_anonymous_page_bytes_never_contain_the_gated_branch(client):
    response = client.get(GATED_URL, headers=RENDER_HEADER)

    body = response.get_data()
    assert response.status_code == 200
    assert b"GATED-PRO-CONTENT" not in body
    assert b">MANAGE-LINK" not in body
    assert b'<div data-vbwd-region="r1">PUBLIC-TEASER</div>' in body


def test_a_viewer_with_the_level_gets_the_true_branch_via_regions(client, create_user):
    _user_id, headers = create_user(access_level_slugs=(PRO_LEVEL_SLUG,))

    response = _regions(client, GATED_URL, headers)

    assert response.status_code == 200
    assert response.get_json()["regions"]["r1"] == "GATED-PRO-CONTENT"


def test_regions_returns_only_the_marked_regions_and_is_never_cached(
    client, create_user
):
    user_id, headers = create_user()

    response = _regions(client, GATED_URL, headers)

    payload = response.get_json()
    assert response.headers["Cache-Control"] == "no-store"
    assert list(payload) == ["regions"]
    assert payload["regions"] == {
        "r1": "PUBLIC-TEASER",
        "r2": "NO-MANAGE-LINK",
        "r3": f"Hello {user_id}",
    }
    assert "fake-gated-title" not in response.get_data(as_text=True)


def test_the_viewer_re_render_receives_the_target_path_and_query(client, create_user):
    user_id, headers = create_user()

    _regions(client, GATED_URL, headers)

    (theme_request,) = received_theme_requests
    assert theme_request.path == "/fake-gated/mug"
    assert dict(theme_request.view_args) == {"item_slug": "mug"}
    assert theme_request.query_args.get("colour") == "red"
    assert theme_request.viewer.user_id == user_id


def test_region_ids_match_between_the_anonymous_page_and_the_viewer_render(
    client, create_user
):
    _user_id, headers = create_user(access_level_slugs=(PRO_LEVEL_SLUG,))

    page_html = client.get(GATED_URL, headers=RENDER_HEADER).get_data(as_text=True)
    regions = _regions(client, GATED_URL, headers).get_json()["regions"]

    assert REGION_ID_PATTERN.findall(page_html) == list(regions)


def test_ids_filter_returns_only_the_requested_regions(client, create_user):
    _user_id, headers = create_user()

    response = _regions(client, GATED_URL, headers, ids="r1,r3")

    assert response.status_code == 200
    assert set(response.get_json()["regions"]) == {"r1", "r3"}


def test_an_id_the_page_does_not_have_is_a_400(client, create_user):
    _user_id, headers = create_user()

    assert _regions(client, GATED_URL, headers, ids="r1,r9").status_code == 400


def test_a_missing_path_is_a_400(client, create_user):
    _user_id, headers = create_user()

    assert client.get(REGIONS_PATH, headers=headers).status_code == 400


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer not.a.valid.token"},
        {"Authorization": "Basic dXNlcjpwYXNz"},
    ],
)
def test_absent_or_bad_token_is_a_401(client, headers):
    assert _regions(client, GATED_URL, headers).status_code == 401


def test_a_profile_refusal_is_a_401(client, create_user, monkeypatch):
    _user_id, headers = create_user()
    monkeypatch.setattr(
        regions_module, "USER_PROFILE_PATH", f"{FAKE_API_PREFIX}/status/403"
    )

    assert _regions(client, GATED_URL, headers).status_code == 401


@pytest.mark.parametrize(
    "path",
    ["/no-such-page", "/api/v1/user/profile", REGIONS_PATH, "/_render/_theme/mode"],
)
def test_a_path_that_is_not_a_theme_page_is_a_404(client, create_user, path):
    _user_id, headers = create_user()

    assert _regions(client, path, headers).status_code == 404


def test_a_page_whose_fe_user_plugin_is_disabled_is_a_404(make_client, create_user):
    _user_id, headers = create_user()
    disabled_client, _app = make_client(
        "theme", owner_enabled=False, api_blueprints=[build_fake_api_blueprint()]
    )

    assert _regions(disabled_client, GATED_URL, headers).status_code == 404


def test_an_inner_api_error_during_the_re_render_maps_to_its_status(
    client, create_user
):
    _user_id, headers = create_user()

    assert _regions(client, "/fake-api-status/404", headers).status_code == 404
    assert _regions(client, "/fake-api-status/429", headers).status_code == 500


def test_regions_endpoint_does_not_exist_in_vue_mode(make_client, create_user):
    _user_id, headers = create_user()
    vue_client, _app = make_client("vue")

    assert _regions(vue_client, GATED_URL, headers).status_code == 404


def test_gdpr_each_user_sees_only_their_own_regions(client, create_user):
    """A regions response for user A never contains user B's data (and vice versa)."""
    first_user_id, first_headers = create_user()
    second_user_id, second_headers = create_user()

    first_body = _regions(client, GATED_URL, first_headers).get_data(as_text=True)
    second_body = _regions(client, GATED_URL, second_headers).get_data(as_text=True)

    assert f"Hello {first_user_id}" in first_body
    assert second_user_id not in first_body
    assert f"Hello {second_user_id}" in second_body
    assert first_user_id not in second_body


def test_the_viewer_re_render_uses_the_same_language_as_the_page(client, create_user):
    _user_id, headers = create_user()
    client.set_cookie("vbwd_lang", "de")

    response = _regions(client, f"{FAKE_LANGUAGE_PAGE_PATH}?page_language=fr", headers)

    assert response.status_code == 200
    assert response.get_json()["regions"] == {"r1": "pre=de greeting=Bonjour"}


def test_every_theme_route_passes_the_route_exposure_audit(theme_app):
    from vbwd.security.route_audit import find_unprotected_routes

    theme_offenders = [
        route.path
        for route in find_unprotected_routes(theme_app)
        if route.path.startswith(("/_render", "/fake-"))
    ]

    assert theme_offenders == []
