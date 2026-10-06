"""``theme_demo`` — a minimal child theme of ``basic`` (S152-11 e2e fixture).

Not a shipped plugin and never listed in ``plugins.json.dist``. It overrides one
template (the CMS ``page`` type, adding a ``theme-demo-banner`` marker) and one
token (``--vbwd-color-primary``) so ``child-theme-override.spec.ts`` can prove the
child-theme contract on a running stack. To use it, copy this directory to
``vbwd-backend/plugins/theme_demo/``, enable it, set the theme config
``active_theme`` to ``demo`` and restart ``api`` — see
``plugins/theme/docs/writing-a-theme.md`` ("Testing").
"""
from pathlib import Path

from vbwd.plugins.base import BasePlugin, PluginMetadata

from plugins.theme.theme.theme_registry import (
    BASIC_THEME_SLUG,
    ThemeDescriptor,
    resolve_theme_registry,
)

THEME_DEMO_SLUG = "demo"

THEME_DEMO_DESCRIPTOR = ThemeDescriptor(
    slug=THEME_DEMO_SLUG,
    name="Demo",
    parent=BASIC_THEME_SLUG,
    root=Path(__file__).resolve().parent / "theme",
)


class ThemeDemoPlugin(BasePlugin):
    """A minimal child theme of ``basic``, used by the theme-mode e2e only."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="theme_demo",
            version="1.0.0",
            author="VBWD Team",
            description="Demo child theme (e2e fixture for the child-theme contract).",
            dependencies=["theme>=1.0"],
        )

    def on_enable(self) -> None:
        theme_registry = resolve_theme_registry()
        if not theme_registry.is_registered(THEME_DEMO_SLUG):
            theme_registry.register(THEME_DEMO_DESCRIPTOR)
