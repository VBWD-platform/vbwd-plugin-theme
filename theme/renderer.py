"""Theme renderer (S152 D1): a sandboxed, autoescaping Jinja2 environment per active theme.

Theme plugins are third-party code, so templates run in a ``SandboxedEnvironment``
with autoescape on. The environment is cached per active theme slug and dropped
by :meth:`ThemeRenderer.invalidate` when the theme config changes. An unknown or
unregistered active slug falls back to ``basic`` and warns once per slug (D9).

``_`` / ``gettext`` translate into the context's ``language``, falling back to
its ``default_language`` and then ``en`` (D13). The languages of the render in
progress live in a context variable, so macros imported without context
translate in the page language too.
"""
import logging
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Set, Tuple

from flask import current_app, url_for
from jinja2 import StrictUndefined, Undefined
from jinja2.sandbox import SandboxedEnvironment

from vbwd.services.asset_storage import asset_dir

from .frontend_mode import read_frontend_mode
from .language_resolver import DEFAULT_LANGUAGE_CONTEXT_KEY, LANGUAGE_CONTEXT_KEY
from .page_registry import THEME_BLUEPRINT_NAME
from .region_tags import (
    REGION_STATE_CONTEXT_KEY,
    RegionRenderState,
    RegionTagsExtension,
)
from .static_assets import ThemeStaticAssets
from .template_loader import ThemeTemplateLoader
from .theme_registry import (
    BASIC_THEME_SLUG,
    TEMPLATES_DIRECTORY,
    THEME_ASSET_OWNER,
    ThemeRegistry,
)
from .theme_request import FALLBACK_LANGUAGE
from .translations import ThemeTranslations
from .viewer import ANONYMOUS_VIEWER, Viewer

logger = logging.getLogger(__name__)

VIEWER_CONTEXT_KEY = "viewer"

# The translation languages of the render in progress (final → default → en).
_render_languages: ContextVar[Tuple[str, ...]] = ContextVar(
    "theme_render_languages", default=(FALLBACK_LANGUAGE,)
)


def translation_languages(context: Mapping[str, Any]) -> Tuple[str, ...]:
    """``(language, default_language, "en")`` from the context, without repeats."""
    candidates = (
        context.get(LANGUAGE_CONTEXT_KEY),
        context.get(DEFAULT_LANGUAGE_CONTEXT_KEY),
        FALLBACK_LANGUAGE,
    )
    return tuple(dict.fromkeys(language for language in candidates if language))


def url_for_page(endpoint: str, **params: Any) -> str:
    return url_for(f"{THEME_BLUEPRINT_NAME}.{endpoint}", **params)


@dataclass(frozen=True)
class RenderedTemplate:
    """The rendered HTML plus the inner HTML of each top-level region, by id."""

    html: str
    regions: Dict[str, str]


class ThemeRenderer:
    """Renders theme templates for the active theme read from the plugin config."""

    def __init__(
        self, theme_registry: ThemeRegistry, read_active_theme_slug: Callable[[], str]
    ) -> None:
        self._theme_registry = theme_registry
        self.static_assets = ThemeStaticAssets(theme_registry)
        self.translations = ThemeTranslations(theme_registry)
        self._read_active_theme_slug = read_active_theme_slug
        self._environments_by_slug: Dict[str, SandboxedEnvironment] = {}
        self._warned_unknown_slugs: Set[str] = set()

    def render(
        self,
        template_name: str,
        context: Mapping[str, Any],
        viewer: Viewer = ANONYMOUS_VIEWER,
    ) -> str:
        """Render for ``viewer`` (anonymous by default) and return the HTML."""
        return self.render_with_regions(template_name, context, viewer).html

    def render_with_regions(
        self,
        template_name: str,
        context: Mapping[str, Any],
        viewer: Viewer = ANONYMOUS_VIEWER,
    ) -> "RenderedTemplate":
        """Render for ``viewer``; also returns each personalised region's inner HTML."""
        environment = self._environment(self.active_theme_slug())
        region_state = RegionRenderState(viewer)
        render_context = dict(context)
        render_context[VIEWER_CONTEXT_KEY] = viewer
        render_context[REGION_STATE_CONTEXT_KEY] = region_state
        languages_token = _render_languages.set(translation_languages(context))
        try:
            html = environment.get_template(template_name).render(render_context)
        finally:
            _render_languages.reset(languages_token)
        return RenderedTemplate(html=html, regions=dict(region_state.contents_by_id))

    def invalidate(self) -> None:
        """Drop cached environments (call when the theme config changes)."""
        self._environments_by_slug.clear()

    def active_theme_slug(self) -> str:
        configured_slug = self._read_active_theme_slug()
        if self._theme_registry.is_registered(configured_slug):
            return configured_slug
        if configured_slug not in self._warned_unknown_slugs:
            self._warned_unknown_slugs.add(configured_slug)
            logger.warning(
                "theme: active theme '%s' is not registered — rendering '%s'",
                configured_slug,
                BASIC_THEME_SLUG,
            )
        return BASIC_THEME_SLUG

    def _environment(self, theme_slug: str) -> SandboxedEnvironment:
        if theme_slug not in self._environments_by_slug:
            self._environments_by_slug[theme_slug] = self._build_environment(theme_slug)
        return self._environments_by_slug[theme_slug]

    def _build_environment(self, theme_slug: str) -> SandboxedEnvironment:
        operator_templates_directory = Path(
            asset_dir(THEME_ASSET_OWNER, theme_slug, TEMPLATES_DIRECTORY)
        )
        environment = SandboxedEnvironment(
            loader=ThemeTemplateLoader(
                self._theme_registry, theme_slug, operator_templates_directory
            ),
            extensions=[RegionTagsExtension],
            autoescape=True,
            undefined=StrictUndefined if current_app.testing else Undefined,
            auto_reload=current_app.debug,
        )

        def asset(path: str) -> str:
            return self.static_assets.asset_url(theme_slug, path)

        def theme_stylesheet_url() -> str:
            return self.static_assets.stylesheet_url(theme_slug)

        def gettext(message: str, **params: Any) -> str:
            return self.translations.translate(
                theme_slug, message, _render_languages.get(), params
            )

        environment.globals.update(
            frontend_mode=read_frontend_mode().value,
            _=gettext,
            gettext=gettext,
            asset=asset,
            theme_stylesheet_url=theme_stylesheet_url,
            url_for_page=url_for_page,
        )
        return environment
