"""S152-04 / D12 — the viewer: access-level and permission predicates, profile parsing."""
import dataclasses

import pytest

from plugins.theme.tests.unit.permission_parity_cases import PERMISSION_PARITY_CASES
from plugins.theme.theme.viewer import (
    ANONYMOUS_VIEWER,
    Viewer,
    viewer_from_profile,
    viewer_has_any_access_level,
    viewer_has_permission,
)


def _viewer(access_level_slugs=(), permissions=()) -> Viewer:
    return Viewer(
        user_id="user-1",
        access_level_slugs=frozenset(access_level_slugs),
        permissions=tuple(permissions),
    )


def test_anonymous_viewer_has_no_identity_levels_or_permissions():
    assert ANONYMOUS_VIEWER.user_id is None
    assert ANONYMOUS_VIEWER.access_level_slugs == frozenset()
    assert ANONYMOUS_VIEWER.permissions == ()


def test_viewer_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        ANONYMOUS_VIEWER.user_id = "someone"


@pytest.mark.parametrize(
    "granted_permissions, requested_permission, expected", PERMISSION_PARITY_CASES
)
def test_permission_wildcards_match_fe_user_has_user_permission(
    granted_permissions, requested_permission, expected
):
    viewer = _viewer(permissions=granted_permissions)

    assert viewer_has_permission(viewer, requested_permission) is expected


def test_anonymous_viewer_has_no_permission():
    assert viewer_has_permission(ANONYMOUS_VIEWER, "booking.manage") is False


def test_access_is_granted_when_the_viewer_holds_any_of_the_slugs():
    viewer = _viewer(access_level_slugs={"gold"})

    assert viewer_has_any_access_level(viewer, ("pro", "gold")) is True


def test_access_is_refused_for_slugs_the_viewer_does_not_hold():
    viewer = _viewer(access_level_slugs={"pro"})

    assert viewer_has_any_access_level(viewer, ("gold",)) is False
    assert viewer_has_any_access_level(viewer, ("no-such-level",)) is False
    assert viewer_has_any_access_level(ANONYMOUS_VIEWER, ("pro",)) is False


def test_viewer_from_profile_reads_id_level_slugs_and_permissions():
    profile = {
        "user": {
            "id": "4f6e0c1e-0000-0000-0000-000000000001",
            "email": "someone@example.com",
            "user_access_levels": [
                {"id": "l1", "slug": "pro", "name": "Pro"},
                {"id": "l2", "slug": "logged-in", "name": "Logged in"},
            ],
            "user_permissions": ["booking.*", "user.profile.view"],
        },
        "details": None,
    }

    viewer = viewer_from_profile(profile)

    assert viewer == Viewer(
        user_id="4f6e0c1e-0000-0000-0000-000000000001",
        access_level_slugs=frozenset({"pro", "logged-in"}),
        permissions=("booking.*", "user.profile.view"),
    )


def test_viewer_from_profile_without_levels_or_permissions_holds_none():
    """A profile without the level/permission fields yields a levelless viewer."""
    viewer = viewer_from_profile({"user": {"id": "user-2"}, "details": None})

    assert viewer == Viewer(
        user_id="user-2", access_level_slugs=frozenset(), permissions=()
    )
