"""Metadata + baseline-config contract for the theme plugin (S152-00b)."""
import json
from pathlib import Path

from plugins.theme import ThemePlugin

PLUGIN_DIRECTORY = Path(__file__).resolve().parents[2]


def _load_plugin_json(file_name: str) -> dict:
    return json.loads((PLUGIN_DIRECTORY / file_name).read_text(encoding="utf-8"))


def test_metadata_name_is_the_manifest_key():
    assert ThemePlugin().metadata.name == "theme"


def test_metadata_version():
    assert ThemePlugin().metadata.version == "1.0.0"


def test_dependencies_are_exactly_declared():
    assert ThemePlugin().metadata.dependencies == []


def test_ships_no_routes_in_vue_mode(monkeypatch):
    monkeypatch.delenv("VBWD_FRONTEND_MODE", raising=False)
    plugin = ThemePlugin()

    assert plugin.get_url_prefix() == ""
    assert plugin.get_blueprint() is None


def test_admin_config_fields_all_exist_in_config():
    config = _load_plugin_json("config.json")
    admin_config = _load_plugin_json("admin-config.json")
    admin_field_keys = [
        field["key"] for tab in admin_config["tabs"] for field in tab["fields"]
    ]

    assert admin_field_keys
    assert set(admin_field_keys) <= set(config)


def test_debug_mode_toggle_defaults_off():
    assert _load_plugin_json("config.json")["debug_mode"]["default"] is False


THEME_PLUGIN_NAMES = [
    "theme",
    "theme_cms",
    "theme_checkout",
    "theme_shop",
    "theme_dataset",
    "theme_subscription",
    "theme_booking",
]
PLUGINS_DIRECTORY = PLUGIN_DIRECTORY.parent


def test_active_theme_defaults_to_basic():
    active_theme = _load_plugin_json("config.json")["active_theme"]

    assert active_theme["type"] == "string"
    assert active_theme["default"] == "basic"


def test_plugins_json_dist_lists_every_theme_plugin_disabled():
    manifest = json.loads(
        (PLUGINS_DIRECTORY / "plugins.json.dist").read_text(encoding="utf-8")
    )["plugins"]

    for plugin_name in THEME_PLUGIN_NAMES:
        assert plugin_name in manifest, plugin_name
        assert manifest[plugin_name]["enabled"] is False, plugin_name


def test_config_json_dist_has_an_entry_for_every_theme_plugin():
    dist_config = json.loads(
        (PLUGINS_DIRECTORY / "config.json.dist").read_text(encoding="utf-8")
    )

    for plugin_name in THEME_PLUGIN_NAMES:
        assert plugin_name in dist_config, plugin_name


def test_the_default_language_policy_is_the_core_one():
    from plugins.theme.theme.language_policy import CoreLanguagePolicy

    assert isinstance(ThemePlugin().language_policy, CoreLanguagePolicy)


def test_set_language_policy_last_write_wins():
    plugin = ThemePlugin()
    from plugins.theme.theme.language_policy import CoreLanguagePolicy

    first_policy, second_policy = CoreLanguagePolicy(), CoreLanguagePolicy()

    plugin.set_language_policy(first_policy)
    plugin.set_language_policy(second_policy)

    assert plugin.language_policy is second_policy
