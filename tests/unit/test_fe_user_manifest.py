"""S152-01 — a themed page answers only while its owner fe-user plugin is enabled."""
import json
import logging
import os

from plugins.theme.theme.fe_user_manifest import CORE_OWNER, FeUserPluginManifest

MANIFEST_VARIABLE = "VBWD_FE_USER_PLUGINS_JSON"


def _write_manifest(path, enabled_by_name) -> None:
    plugins = {name: {"enabled": enabled} for name, enabled in enabled_by_name.items()}
    path.write_text(json.dumps({"plugins": plugins}), encoding="utf-8")


def test_reports_enabled_and_disabled_plugins(tmp_path, monkeypatch):
    manifest_path = tmp_path / "fe-user-plugins.json"
    _write_manifest(manifest_path, {"cms": True, "shop": False})
    monkeypatch.setenv(MANIFEST_VARIABLE, str(manifest_path))
    manifest = FeUserPluginManifest()

    assert manifest.is_enabled("cms") is True
    assert manifest.is_enabled("shop") is False
    assert manifest.is_enabled("unknown") is False


def test_rereads_when_the_file_changes(tmp_path, monkeypatch):
    manifest_path = tmp_path / "fe-user-plugins.json"
    _write_manifest(manifest_path, {"cms": True})
    monkeypatch.setenv(MANIFEST_VARIABLE, str(manifest_path))
    manifest = FeUserPluginManifest()
    assert manifest.is_enabled("cms") is True

    _write_manifest(manifest_path, {"cms": False})
    later = os.stat(manifest_path).st_mtime_ns + 1_000_000_000
    os.utime(manifest_path, ns=(later, later))

    assert manifest.is_enabled("cms") is False


def test_missing_manifest_means_none_enabled_and_logs_once(
    tmp_path, monkeypatch, caplog
):
    monkeypatch.setenv(MANIFEST_VARIABLE, str(tmp_path / "absent.json"))
    manifest = FeUserPluginManifest()

    with caplog.at_level(logging.WARNING):
        assert manifest.is_enabled("cms") is False
        assert manifest.is_enabled("cms") is False

    warnings = [
        record for record in caplog.records if "fe-user manifest" in record.message
    ]
    assert len(warnings) == 1


def test_unset_variable_means_none_enabled(monkeypatch):
    monkeypatch.delenv(MANIFEST_VARIABLE, raising=False)

    assert FeUserPluginManifest().is_enabled("cms") is False


def test_malformed_manifest_means_none_enabled(tmp_path, monkeypatch):
    manifest_path = tmp_path / "fe-user-plugins.json"
    manifest_path.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv(MANIFEST_VARIABLE, str(manifest_path))

    assert FeUserPluginManifest().is_enabled("cms") is False


def test_core_owner_is_always_enabled_even_without_a_manifest(tmp_path, monkeypatch):
    """S152-07 — fe-user core pages (``/login``) have no plugin toggle: always on."""
    monkeypatch.setenv(MANIFEST_VARIABLE, str(tmp_path / "absent.json"))
    manifest = FeUserPluginManifest()

    assert manifest.is_enabled(CORE_OWNER) is True
    assert manifest.is_enabled("cms") is False


def test_a_manifest_entry_cannot_disable_the_core_owner(tmp_path, monkeypatch):
    manifest_path = tmp_path / "fe-user-plugins.json"
    _write_manifest(manifest_path, {CORE_OWNER: False})
    monkeypatch.setenv(MANIFEST_VARIABLE, str(manifest_path))

    assert FeUserPluginManifest().is_enabled(CORE_OWNER) is True
