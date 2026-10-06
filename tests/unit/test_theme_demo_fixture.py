"""S152-11 — the ``theme_demo`` child-theme fixture honours the child-theme contract.

The fixture lives in ``tests/fixtures/theme_demo`` and is copied into ``plugins/``
only for the theme-mode e2e ``child-theme-override.spec.ts``. These tests keep it
loadable: it registers cleanly on top of ``basic``, its template override wins over
the adapter-contributed template, and its token lands in the merged ``:root`` block.
"""
import json
from pathlib import Path

from jinja2 import Environment

from plugins.theme.tests.fixtures.theme_demo import (
    THEME_DEMO_DESCRIPTOR,
    THEME_DEMO_SLUG,
    ThemeDemoPlugin,
)
from plugins.theme.theme.static_assets import PUBLIC_SURFACE
from plugins.theme.theme.stylesheet import StylesheetBuilder
from plugins.theme.theme.template_loader import ThemeTemplateLoader
from plugins.theme.theme.theme_registry import (
    BASIC_THEME_DESCRIPTOR,
    BASIC_THEME_SLUG,
    ThemeRegistry,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "theme_demo"
PLUGINS_DIST_MANIFEST = Path(__file__).resolve().parents[3] / "plugins.json.dist"
OVERRIDDEN_TEMPLATE = "cms/page_types/page.html.j2"
DEMO_PRIMARY_COLOUR = "#0a7f6f"
DEMO_BANNER_TEST_ID = 'data-testid="theme-demo-banner"'


def _registry_with_demo() -> ThemeRegistry:
    registry = ThemeRegistry()
    registry.register(BASIC_THEME_DESCRIPTOR)
    registry.register(THEME_DEMO_DESCRIPTOR)
    return registry


def test_demo_registers_as_a_child_of_basic():
    registry = _registry_with_demo()

    assert THEME_DEMO_DESCRIPTOR.parent == BASIC_THEME_SLUG
    assert registry.chain(THEME_DEMO_SLUG) == [THEME_DEMO_SLUG, BASIC_THEME_SLUG]


def test_demo_page_template_wins_over_the_contributed_template(tmp_path):
    registry = _registry_with_demo()
    contributed_directory = tmp_path / "contributed"
    (contributed_directory / "cms" / "page_types").mkdir(parents=True)
    (contributed_directory / OVERRIDDEN_TEMPLATE).write_text("contributed page")
    registry.add_contributed_template_path(contributed_directory)
    loader = ThemeTemplateLoader(registry, THEME_DEMO_SLUG, tmp_path / "operator")

    source, _, _ = loader.get_source(Environment(), OVERRIDDEN_TEMPLATE)

    assert DEMO_BANNER_TEST_ID in source
    assert '{% extends "cms/page_base.html.j2" %}' in source


def test_demo_primary_colour_token_lands_in_the_root_block():
    registry = _registry_with_demo()
    descriptors_basic_first = [
        registry.get(slug) for slug in reversed(registry.chain(THEME_DEMO_SLUG))
    ]

    stylesheet = StylesheetBuilder().build(descriptors_basic_first, PUBLIC_SURFACE)

    assert f"--vbwd-color-primary: {DEMO_PRIMARY_COLOUR};" in stylesheet.css_text
    assert ".theme-demo-banner" in stylesheet.css_text


def test_demo_plugin_depends_only_on_the_theme_platform():
    metadata = ThemeDemoPlugin().metadata

    assert metadata.name == "theme_demo"
    assert metadata.dependencies == ["theme>=1.0"]


def test_demo_ships_both_baseline_config_files_with_debug_mode():
    config = json.loads((FIXTURE_ROOT / "config.json").read_text())
    admin_config = json.loads((FIXTURE_ROOT / "admin-config.json").read_text())

    assert "debug_mode" in config
    admin_field_keys = [
        field["key"] for tab in admin_config["tabs"] for field in tab["fields"]
    ]
    assert "debug_mode" in admin_field_keys


def test_demo_is_never_registered_in_the_distributed_manifest():
    manifest = json.loads(PLUGINS_DIST_MANIFEST.read_text())

    assert "theme_demo" not in manifest["plugins"]
