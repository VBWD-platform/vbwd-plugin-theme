"""Which fe-user plugins are enabled — read from the shared fe-user manifest.

A themed page answers only while its owner fe-user plugin is enabled, so a
disabled plugin's URL 404s and nginx falls back to the SPA. The manifest path
comes from ``VBWD_FE_USER_PLUGINS_JSON`` and is re-read only when its mtime
changes. A missing or unreadable manifest means "none enabled" (logged once).
"""
import logging
import os
from typing import FrozenSet, Optional, Tuple

from vbwd.services.filesystem import LocalFilesystemManager

logger = logging.getLogger(__name__)

FE_USER_MANIFEST_ENVIRONMENT_VARIABLE = "VBWD_FE_USER_PLUGINS_JSON"

# The owner of fe-user CORE pages (``/login``): core has no plugin toggle, so its
# pages are always enabled — the same name the D11 route-coverage oracle uses.
CORE_OWNER = "core"

# The core namespace whose locked-read policy governs the plugin manifests
# (the same one ``vbwd/routes/admin/frontend_plugins.py`` writes through).
_MANIFEST_NAMESPACE = "plugins"


class FeUserPluginManifest:
    """Answers ``is_enabled(plugin_name)`` from the fe-user manifest."""

    def __init__(self) -> None:
        self._cache_key: Optional[Tuple[str, int]] = None
        self._enabled_plugin_names: FrozenSet[str] = frozenset()
        self._unreadable_logged = False

    def is_enabled(self, plugin_name: str) -> bool:
        if plugin_name == CORE_OWNER:
            return True
        return plugin_name in self._current_enabled_plugin_names()

    def _current_enabled_plugin_names(self) -> FrozenSet[str]:
        manifest_path = os.environ.get(FE_USER_MANIFEST_ENVIRONMENT_VARIABLE)
        if not manifest_path:
            return self._none_enabled("is not set")
        try:
            cache_key = (manifest_path, os.stat(manifest_path).st_mtime_ns)
        except OSError:
            return self._none_enabled(f"'{manifest_path}' does not exist")
        if cache_key == self._cache_key:
            return self._enabled_plugin_names
        manifest = self._read_manifest(manifest_path)
        if not isinstance(manifest, dict):
            return self._none_enabled(f"'{manifest_path}' is not readable JSON")
        plugin_entries = manifest.get("plugins") or {}
        self._enabled_plugin_names = frozenset(
            plugin_name
            for plugin_name, entry in plugin_entries.items()
            if isinstance(entry, dict) and entry.get("enabled") is True
        )
        self._cache_key = cache_key
        self._unreadable_logged = False
        return self._enabled_plugin_names

    @staticmethod
    def _read_manifest(manifest_path: str) -> object:
        filesystem = LocalFilesystemManager(
            namespace_roots={_MANIFEST_NAMESPACE: os.path.dirname(manifest_path)}
        )
        try:
            return filesystem.read_json(
                _MANIFEST_NAMESPACE, os.path.basename(manifest_path), default=None
            )
        except OSError:
            return None

    def _none_enabled(self, reason: str) -> FrozenSet[str]:
        self._cache_key = None
        self._enabled_plugin_names = frozenset()
        if not self._unreadable_logged:
            logger.warning(
                "[theme] fe-user manifest %s %s — no themed page will answer",
                FE_USER_MANIFEST_ENVIRONMENT_VARIABLE,
                reason,
            )
            self._unreadable_logged = True
        return self._enabled_plugin_names
