"""Integration fixtures: a real ``create_app`` booted with only theme + the fake adapter.

Boot is narrowed to exactly the theme plugin plus the test-only fake adapter (no
real adapter, no domain plugin), so the route table is deterministic locally
and in an isolated CI clone. ``load_persisted_state`` is replaced by a stand-in
that enables theme, then the adapter — the order the core uses.
"""
import json

import pytest

from vbwd.plugins.manager import PluginManager

from plugins.theme.tests.integration.fake_adapter import (
    FAKE_ADAPTER_NAME,
    FAKE_OWNER_PLUGIN,
    FakeThemeAdapterPlugin,
    received_api_error_statuses,
    received_theme_requests,
)


def _enable_only_theme_and_fake_adapter(plugin_manager: PluginManager) -> None:
    """Stands in for ``load_persisted_state``: enable theme, then the adapter."""
    plugin_manager.register_plugin(FakeThemeAdapterPlugin())
    plugin_manager.initialize_plugin(FAKE_ADAPTER_NAME)
    for plugin_name in ("theme", FAKE_ADAPTER_NAME):
        plugin = plugin_manager.get_plugin(plugin_name)
        plugin.validate_environment()
        plugin.enable()


def _write_fe_user_manifest(path, owner_enabled: bool) -> None:
    manifest = {"plugins": {FAKE_OWNER_PLUGIN: {"enabled": owner_enabled}}}
    path.write_text(json.dumps(manifest), encoding="utf-8")


@pytest.fixture
def make_client(monkeypatch, tmp_path):
    """Build a booted app in the given mode; returns ``(client, app)``.

    ``extra_config`` is merged into the app config; ``api_blueprints`` are
    test-only ``/api/v1`` blueprints mounted the way create_app mounts API
    blueprints (CSRF-exempt).
    """
    from vbwd.app import create_app
    from vbwd.config import get_database_url
    from vbwd.extensions import csrf

    monkeypatch.setattr(
        PluginManager, "load_persisted_state", _enable_only_theme_and_fake_adapter
    )
    monkeypatch.setenv("VBWD_VAR_DIR", str(tmp_path / "var"))
    manifest_path = tmp_path / "fe-user-plugins.json"
    monkeypatch.setenv("VBWD_FE_USER_PLUGINS_JSON", str(manifest_path))
    received_theme_requests.clear()
    received_api_error_statuses.clear()

    def build(mode: str, owner_enabled=True, extra_config=None, api_blueprints=()):
        monkeypatch.setenv("VBWD_FRONTEND_MODE", mode)
        if owner_enabled is not None:
            _write_fe_user_manifest(manifest_path, owner_enabled)
        app_config = {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": get_database_url(),
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "RATELIMIT_ENABLED": False,
        }
        app_config.update(extra_config or {})
        app = create_app(app_config)
        for blueprint in api_blueprints:
            csrf.exempt(blueprint)
            app.register_blueprint(blueprint)
        return app.test_client(), app

    return build
