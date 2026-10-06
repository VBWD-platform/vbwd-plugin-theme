"""S152-06b — the theme fragment registry: htmx islands an adapter serves under
``/_render/_fragment/`` (a quick-search dropdown, a form result).

A fragment is NOT a page: it lives under the theme-internal prefix (W2), needs
no ``X-VBWD-Render`` marker, answers GET (and POST only when declared) and is
declared public (GET → read, POST → mutation) for the route-exposure audit.
"""
import pytest

from plugins.theme import ThemePlugin
from plugins.theme.theme.fragment_registry import (
    ThemeFragment,
    ThemeFragmentRegistrationError,
    ThemeFragmentRegistry,
)


def _fragment(
    rule="/_render/_fragment/fake/echo", endpoint="fake_echo", methods=("GET",)
):
    return ThemeFragment(
        rule=rule,
        endpoint=endpoint,
        owner_fe_user_plugin="fake-fe-user-plugin",
        template="fake/fragment.html.j2",
        build_context=lambda theme_request: {},
        methods=methods,
    )


def test_a_fragment_under_the_fragment_prefix_is_registered():
    registry = ThemeFragmentRegistry()

    registry.register(_fragment())

    assert [fragment.rule for fragment in registry.fragments()] == [
        "/_render/_fragment/fake/echo"
    ]


def test_methods_default_to_get_only():
    fragment = ThemeFragment(
        rule="/_render/_fragment/fake/x",
        endpoint="x",
        owner_fe_user_plugin="fake-fe-user-plugin",
        template="fake/fragment.html.j2",
        build_context=lambda theme_request: {},
    )

    assert fragment.methods == ("GET",)


@pytest.mark.parametrize(
    "refused_rule",
    [
        "/fake/echo",
        "/_render/fake/echo",
        "/_render/_fragmentx/echo",
        "/_render/_fragment",
        "/_render/_fragment/regions",
    ],
)
def test_a_rule_outside_the_fragment_prefix_or_the_regions_path_is_refused(
    refused_rule,
):
    with pytest.raises(ThemeFragmentRegistrationError, match="fragment"):
        ThemeFragmentRegistry().register(_fragment(rule=refused_rule))


@pytest.mark.parametrize("methods", [(), ("PUT",), ("GET", "DELETE"), ("get",)])
def test_only_get_and_post_are_allowed(methods):
    with pytest.raises(ThemeFragmentRegistrationError, match="methods"):
        ThemeFragmentRegistry().register(_fragment(methods=methods))


def test_duplicate_rule_and_duplicate_endpoint_are_refused():
    registry = ThemeFragmentRegistry()
    registry.register(_fragment())

    with pytest.raises(ThemeFragmentRegistrationError, match="already registered"):
        registry.register(_fragment(endpoint="other"))
    with pytest.raises(ThemeFragmentRegistrationError, match="endpoint"):
        registry.register(_fragment(rule="/_render/_fragment/fake/other"))


def test_a_sealed_registry_refuses_a_late_fragment():
    registry = ThemeFragmentRegistry()
    registry.seal()

    with pytest.raises(ThemeFragmentRegistrationError, match="after"):
        registry.register(_fragment())


def test_the_theme_plugin_owns_a_fragment_registry_sealed_at_mount(monkeypatch):
    monkeypatch.delenv("VBWD_FRONTEND_MODE", raising=False)
    plugin = ThemePlugin()

    plugin.get_blueprint()

    with pytest.raises(ThemeFragmentRegistrationError, match="after"):
        plugin.fragment_registry.register(_fragment())


def test_get_fragments_are_public_reads_and_post_fragments_public_mutations():
    plugin = ThemePlugin()
    plugin.fragment_registry.register(_fragment())
    plugin.fragment_registry.register(
        _fragment(
            rule="/_render/_fragment/fake/form",
            endpoint="fake_form",
            methods=("POST",),
        )
    )

    declaration = plugin.declare_public_routes()

    assert "/_render/_fragment/fake/echo" in declaration.read
    assert "/_render/_fragment/fake/echo" not in declaration.mutation
    assert "/_render/_fragment/fake/form" in declaration.mutation
    assert "/_render/_fragment/fake/form" not in declaration.read
