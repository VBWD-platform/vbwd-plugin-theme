"""Server-rendered theme platform (Jinja2) for the public fe-user pages (S152).

Renders only when ``VBWD_FRONTEND_MODE=theme``; in the default ``vue`` mode the
theme mounts no page route and the Vue SPA serves every page. Adapters register
their pages into :class:`ThemePageRegistry` and their htmx islands into
:class:`ThemeFragmentRegistry` from ``on_enable``.
"""
from typing import TYPE_CHECKING, Optional

from flask import current_app

from vbwd.plugins.base import BasePlugin, PluginMetadata, PublicRouteDeclaration

from plugins.theme.theme.fe_user_manifest import FeUserPluginManifest
from plugins.theme.theme.fragment_registry import READ_METHOD, ThemeFragmentRegistry
from plugins.theme.theme.frontend_mode import FrontendMode, read_frontend_mode
from plugins.theme.theme.language_policy import CoreLanguagePolicy, ThemeLanguagePolicy
from plugins.theme.theme.language_resolver import ThemeLanguageResolver
from plugins.theme.theme.login import register_login
from plugins.theme.theme.page_registry import ThemePageRegistry
from plugins.theme.theme.renderer import ThemeRenderer
from plugins.theme.theme.routes import (
    MODE_PROBE_PATH,
    STATIC_ASSET_RULE,
    build_theme_blueprint,
)
from plugins.theme.theme.static_assets import THEME_STYLESHEET_PATH
from plugins.theme.theme.theme_registry import (
    BASIC_THEME_DESCRIPTOR,
    BASIC_THEME_SLUG,
    ThemeRegistry,
)

if TYPE_CHECKING:
    from flask import Blueprint

ACTIVE_THEME_CONFIG_KEY = "active_theme"


class ThemePlugin(BasePlugin):
    """Server-rendered theme platform (Jinja2) for the public fe-user pages."""

    def __init__(self) -> None:
        super().__init__()
        self.page_registry = ThemePageRegistry()
        self.fragment_registry = ThemeFragmentRegistry()
        self.theme_registry = ThemeRegistry()
        self.renderer = ThemeRenderer(self.theme_registry, self.read_active_theme_slug)
        self.language_resolver = ThemeLanguageResolver(CoreLanguagePolicy())
        self._fe_user_manifest = FeUserPluginManifest()

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="theme",
            version="1.0.0",
            author="VBWD Team",
            description="Server-rendered theme platform (Jinja2) for the public fe-user pages.",
            dependencies=[],
        )

    def validate_environment(self) -> None:
        """D10 — an invalid ``VBWD_FRONTEND_MODE`` fails boot (C1)."""
        read_frontend_mode()

    def on_enable(self) -> None:
        if not self.theme_registry.is_registered(BASIC_THEME_SLUG):
            self.theme_registry.register(BASIC_THEME_DESCRIPTOR)
        # fe-user core's /login is on the purchase path: the platform themes it (S152-07).
        register_login(self.page_registry, self.fragment_registry)

    @property
    def language_policy(self) -> ThemeLanguagePolicy:
        return self.language_resolver.policy

    def set_language_policy(self, policy: ThemeLanguagePolicy) -> None:
        """D13 seam — the CMS defines language: ``theme_cms`` registers its policy here
        from ``on_enable`` (last write wins). The default reads core's language list.
        """
        self.language_resolver.set_policy(policy)

    def read_active_theme_slug(self) -> str:
        """``active_theme`` as the operator saved it (shared config store), else basic."""
        config_store = getattr(current_app, "config_store", None)
        saved_config = (
            config_store.get_config(self.metadata.name) if config_store else {}
        )
        return saved_config.get(ACTIVE_THEME_CONFIG_KEY) or BASIC_THEME_SLUG

    def get_blueprint(self) -> Optional["Blueprint"]:
        """Built once at mount time; the registry is sealed in both modes."""
        self.page_registry.seal()
        self.fragment_registry.seal()
        if read_frontend_mode() is not FrontendMode.THEME:
            return None
        return build_theme_blueprint(
            self.page_registry,
            self._fe_user_manifest,
            self.renderer,
            self.language_resolver,
            self.fragment_registry,
        )

    def get_url_prefix(self) -> Optional[str]:
        # Pages mount at their public paths (W2); the probe is absolute.
        return ""

    def declare_public_routes(self) -> PublicRouteDeclaration:
        read_routes = {
            MODE_PROBE_PATH: "frontend-mode probe for the e2e sentinel (D10)",
            THEME_STYLESHEET_PATH: "the active theme's public stylesheet (D8)",
            STATIC_ASSET_RULE: "bundled theme static files (CSS, runtime JS)",
        }
        for page in self.page_registry.pages():
            read_routes[page.rule] = (
                f"themed page of fe-user plugin '{page.owner_fe_user_plugin}'; "
                "identity-dependent parts load as personalised regions (D4)"
            )
        mutation_routes = {}
        for fragment in self.fragment_registry.fragments():
            justification = (
                f"htmx fragment of fe-user plugin '{fragment.owner_fe_user_plugin}'; "
                "proxies the same public /api/v1 endpoint the SPA calls (C2)"
            )
            if READ_METHOD in fragment.methods:
                read_routes[fragment.rule] = justification
            if set(fragment.methods) - {READ_METHOD}:
                mutation_routes[fragment.rule] = justification
        return PublicRouteDeclaration(read=read_routes, mutation=mutation_routes)
