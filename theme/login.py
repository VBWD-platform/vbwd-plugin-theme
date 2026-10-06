"""The themed ``/login`` — the twin of fe-user core ``views/Login.vue`` (S152-07 A).

``/login`` belongs to fe-user core (owner :data:`CORE_OWNER`, always enabled),
so the theme platform renders it itself. The form posts through htmx to
:data:`LOGIN_FRAGMENT_PATH`, which calls the SAME ``POST /api/v1/auth/login``
the SPA calls (``call_api``, D3) and answers either the SPA's error message or a
``data-vbwd-session`` directive: the runtime stores the SPA's localStorage keys
and navigates to the redirect target, exactly as ``Login.vue`` does.
"""
from typing import Any, Dict, Optional

from .fe_user_manifest import CORE_OWNER
from .fragment_registry import ThemeFragment, ThemeFragmentRegistry
from .page_registry import PUBLIC_PAGE, ThemePage, ThemePageRegistry
from .theme_api import ThemeApiError, call_api
from .theme_request import ThemeRequest

LOGIN_PAGE_PATH = "/login"
LOGIN_FRAGMENT_PATH = "/_render/_fragment/login"
LOGIN_API_PATH = "/api/v1/auth/login"
LOGIN_PAGE_TEMPLATE = "_shared/auth/login.html.j2"
LOGIN_RESULT_TEMPLATE = "_shared/auth/login_result.html.j2"
DASHBOARD_PATH = "/dashboard"
REDIRECT_PARAMETER = "redirect"
LOGIN_PAGE_PRIORITY = 50
POST_METHOD = "POST"


def safe_redirect_target(raw_target: Optional[str]) -> Optional[str]:
    """Where to go after login: ``None`` when no target was asked for (the runtime
    then reads the SPA's ``redirect_after_login`` session value); a same-origin
    path otherwise; ``/dashboard`` for an off-site URL or anything under ``/login``
    (``Login.vue`` never chains back into ``/login``).
    """
    if not raw_target:
        return None
    is_same_origin_path = (
        raw_target.startswith("/")
        and not raw_target.startswith("//")
        and not raw_target.startswith("/\\")
    )
    if not is_same_origin_path or raw_target.startswith(LOGIN_PAGE_PATH):
        return DASHBOARD_PATH
    return raw_target


def login_page_context(theme_request: ThemeRequest) -> Dict[str, Any]:
    """The raw ``redirect`` query value, carried to the fragment in a hidden field."""
    return {"redirect": theme_request.query_args.get(REDIRECT_PARAMETER) or ""}


def login_result_context(theme_request: ThemeRequest) -> Dict[str, Any]:
    """``POST /api/v1/auth/login``: the session directive, or the error to show.

    ``error_message`` ``None`` renders the translated "Login failed" default.
    """
    form = theme_request.query_args
    try:
        body = call_api(
            theme_request,
            POST_METHOD,
            LOGIN_API_PATH,
            json={"email": form.get("email", ""), "password": form.get("password", "")},
        )
    except ThemeApiError as refusal:
        return {"session": None, "error_message": refusal.message or None}
    if not body.get("success") or not body.get("token"):
        return {"session": None, "error_message": body.get("error") or None}
    user = body.get("user") or {}
    return {
        "session": {
            "token": body["token"],
            "user_id": body.get("user_id"),
            "user_permissions": user.get("user_permissions") or [],
            "redirect": safe_redirect_target(form.get(REDIRECT_PARAMETER)),
        },
        "error_message": None,
    }


LOGIN_PAGE = ThemePage(
    rule=LOGIN_PAGE_PATH,
    endpoint="core_login",
    owner_fe_user_plugin=CORE_OWNER,
    priority=LOGIN_PAGE_PRIORITY,
    auth=PUBLIC_PAGE,
    template=LOGIN_PAGE_TEMPLATE,
    build_context=login_page_context,
)

LOGIN_FRAGMENT = ThemeFragment(
    rule=LOGIN_FRAGMENT_PATH,
    endpoint="core_login_fragment",
    owner_fe_user_plugin=CORE_OWNER,
    template=LOGIN_RESULT_TEMPLATE,
    build_context=login_result_context,
    methods=(POST_METHOD,),
)


def register_login(
    page_registry: ThemePageRegistry, fragment_registry: ThemeFragmentRegistry
) -> None:
    """Register the login page + fragment once (``on_enable`` may run again)."""
    if any(page.rule == LOGIN_PAGE_PATH for page in page_registry.pages()):
        return
    page_registry.register(LOGIN_PAGE)
    fragment_registry.register(LOGIN_FRAGMENT)
