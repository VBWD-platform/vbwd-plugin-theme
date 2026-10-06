"""S152-01 / D7 + W2 — the theme page registry refuses SPA-only and internal paths."""
import pytest

from plugins.theme import ThemePlugin
from plugins.theme.theme.page_registry import (
    ThemePage,
    ThemePageRegistrationError,
    ThemePageRegistry,
)


def _page(rule: str, endpoint: str = "fake_page", priority: int = 0) -> ThemePage:
    return ThemePage(
        rule=rule,
        endpoint=endpoint,
        owner_fe_user_plugin="fake-fe-user-plugin",
        priority=priority,
        auth="public",
        template="fake/page.html.j2",
        build_context=lambda theme_request: {},
    )


@pytest.mark.parametrize(
    "refused_rule",
    [
        "/dashboard",
        "/dashboard/x",
        "/dashboard/<path:rest>",
        "/tuktuk/chat",
        "/_render/x",
    ],
)
def test_router_refuses_dashboard_and_account_area_routes(refused_rule):
    with pytest.raises(ThemePageRegistrationError, match="reserved prefix"):
        ThemePageRegistry().register(_page(refused_rule))


def test_allows_a_path_that_only_shares_the_letters_of_a_prefix():
    registry = ThemePageRegistry()

    registry.register(_page("/dashboards-explained"))

    assert [page.rule for page in registry.pages()] == ["/dashboards-explained"]


def test_duplicate_rule_is_refused():
    registry = ThemePageRegistry()
    registry.register(_page("/shop", endpoint="shop_one"))

    with pytest.raises(ThemePageRegistrationError, match="already registered"):
        registry.register(_page("/shop", endpoint="shop_two"))


def test_duplicate_endpoint_is_refused():
    registry = ThemePageRegistry()
    registry.register(_page("/shop", endpoint="catalogue"))

    with pytest.raises(ThemePageRegistrationError, match="endpoint"):
        registry.register(_page("/store", endpoint="catalogue"))


def test_unknown_auth_level_is_refused():
    page = ThemePage(
        rule="/shop",
        endpoint="shop",
        owner_fe_user_plugin="shop",
        priority=0,
        auth="admin",
        template="shop/catalogue.html.j2",
        build_context=lambda theme_request: {},
    )

    with pytest.raises(ThemePageRegistrationError, match="auth"):
        ThemePageRegistry().register(page)


def test_pages_are_listed_highest_priority_first():
    registry = ThemePageRegistry()
    registry.register(_page("/low", endpoint="low", priority=1))
    registry.register(_page("/high", endpoint="high", priority=9))

    assert [page.rule for page in registry.pages()] == ["/high", "/low"]


def test_registration_after_the_blueprint_was_built_raises(monkeypatch):
    monkeypatch.setenv("VBWD_FRONTEND_MODE", "theme")
    plugin = ThemePlugin()
    plugin.get_blueprint()

    with pytest.raises(ThemePageRegistrationError, match="after the theme blueprint"):
        plugin.page_registry.register(_page("/late"))


def test_registration_after_mount_raises_in_vue_mode_too(monkeypatch):
    monkeypatch.setenv("VBWD_FRONTEND_MODE", "vue")
    plugin = ThemePlugin()
    assert plugin.get_blueprint() is None

    with pytest.raises(ThemePageRegistrationError, match="after the theme blueprint"):
        plugin.page_registry.register(_page("/late"))


def test_registered_pages_are_declared_public_reads():
    plugin = ThemePlugin()
    plugin.page_registry.register(_page("/shop"))

    declared_reads = plugin.declare_public_routes().read

    assert set(declared_reads) == {
        "/_render/_theme/mode",
        "/_render/_theme/public/theme.css",
        "/_render/_theme/static/<theme_slug>/<path:asset_path>",
        "/shop",
    }
