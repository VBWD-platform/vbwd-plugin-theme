"""Who a themed render is for (S152 D4 + D12).

Page navigations carry no bearer, so every page render is for
:data:`ANONYMOUS_VIEWER`. A real viewer exists only while the regions endpoint
re-renders a page for the token holder.
"""
from dataclasses import dataclass
from typing import Any, FrozenSet, Iterable, Mapping, Optional, Tuple


@dataclass(frozen=True)
class Viewer:
    """The identity a render is personalised for."""

    user_id: Optional[str]
    access_level_slugs: FrozenSet[str]
    permissions: Tuple[str, ...]


ANONYMOUS_VIEWER = Viewer(user_id=None, access_level_slugs=frozenset(), permissions=())


PERMISSION_WILDCARD = "*"
ALL_PERMISSIONS = PERMISSION_WILDCARD
PERMISSION_WILDCARD_SUFFIX = "." + PERMISSION_WILDCARD


def viewer_has_permission(viewer: Viewer, permission: str) -> bool:
    """Same wildcard semantics as fe-user ``hasUserPermission`` (``*`` and ``prefix.*``)."""
    if ALL_PERMISSIONS in viewer.permissions or permission in viewer.permissions:
        return True
    return any(
        granted.endswith(PERMISSION_WILDCARD_SUFFIX)
        and permission.startswith(granted.removesuffix(PERMISSION_WILDCARD))
        for granted in viewer.permissions
    )


def viewer_has_any_access_level(viewer: Viewer, slugs: Iterable[str]) -> bool:
    """True iff the viewer holds at least one of ``slugs``; unknown slugs never match."""
    return not viewer.access_level_slugs.isdisjoint(slugs)


def viewer_from_profile(profile: Mapping[str, Any]) -> Viewer:
    """The viewer described by a ``GET /api/v1/user/profile`` body.

    Reads ``user.id``, ``user.user_access_levels[].slug`` and
    ``user.user_permissions`` (the core ``UserDataSchema`` field names). A
    profile without the level/permission fields yields a levelless viewer, so
    gated branches stay closed — never open.
    """
    user = profile.get("user") or {}
    return Viewer(
        user_id=str(user["id"]),
        access_level_slugs=frozenset(
            level["slug"] for level in user.get("user_access_levels") or ()
        ),
        permissions=tuple(user.get("user_permissions") or ()),
    )
