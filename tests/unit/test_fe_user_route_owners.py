"""S154 D9 — plugins that own public fe-user SPA routes, discovered structurally.

A domain plugin whose fe-user companion mounts public routes under an
operator-configurable base (ghrm's catalogue) declares them through
``fe_user_route_prefixes()``. Domain plugins never import the theme (S152 R1),
so the theme finds these owners by shape among the enabled plugins; the theme
and its adapters never name the domain plugin or hardcode its base.
"""
from types import SimpleNamespace

from flask import Flask

from plugins.theme.theme.page_registry import (
    FeUserRouteOwner,
    collect_fe_user_route_prefixes,
    is_under_any_prefix,
    resolve_fe_user_route_prefixes,
)


class _RouteOwningPlugin:
    def __init__(self, *prefixes: str) -> None:
        self._prefixes = list(prefixes)

    def fe_user_route_prefixes(self):
        return self._prefixes


class _PlainPlugin:
    """A plugin with no fe-user routes to hand back: never consulted."""


def test_a_plugin_with_the_method_is_an_owner_without_importing_the_theme():
    assert isinstance(_RouteOwningPlugin("/my-catalogue"), FeUserRouteOwner)
    assert not isinstance(_PlainPlugin(), FeUserRouteOwner)


def test_prefixes_are_collected_from_every_owner_and_plain_plugins_are_skipped():
    plugins = [
        _RouteOwningPlugin("/my-catalogue", "/auth-callbacks"),
        _PlainPlugin(),
        _RouteOwningPlugin("/vendor-area"),
    ]

    assert collect_fe_user_route_prefixes(plugins) == [
        "/my-catalogue",
        "/auth-callbacks",
        "/vendor-area",
    ]


def test_a_prefix_that_would_swallow_every_path_or_is_not_absolute_is_ignored():
    plugins = [_RouteOwningPlugin("/", "", "relative", "/kept")]

    assert collect_fe_user_route_prefixes(plugins) == ["/kept"]


def test_match_is_segment_wise():
    prefixes = ["/my-catalogue"]

    assert is_under_any_prefix("/my-catalogue", prefixes)
    assert is_under_any_prefix("/my-catalogue/some-package", prefixes)
    assert not is_under_any_prefix("/my-catalogues", prefixes)
    assert not is_under_any_prefix("/other", prefixes)


def test_resolution_reads_only_the_enabled_plugins_of_the_running_app():
    application = Flask(__name__)
    application.plugin_manager = SimpleNamespace(
        get_enabled_plugins=lambda: [_RouteOwningPlugin("/my-catalogue")]
    )

    with application.app_context():
        assert resolve_fe_user_route_prefixes() == ["/my-catalogue"]
