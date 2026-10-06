"""Theme static assets (S152-03): chain-resolved files and their content-hashed URLs.

A static path under ``/_render/_theme/static/<slug>/`` resolves first-hit-wins
through that theme's chain (the theme, its parents, ``basic``), the same order
templates use, so a child theme inherits basic's runtime scripts. Every lookup
goes through werkzeug ``safe_join``: traversal and absolute paths resolve to
nothing.
"""
from pathlib import Path
from typing import Optional

from werkzeug.security import safe_join

from .stylesheet import Stylesheet, StylesheetBuilder, content_hash
from .theme_registry import ThemeRegistry

THEME_STATIC_URL_PREFIX = "/_render/_theme/static"
THEME_STYLESHEET_PATH = "/_render/_theme/public/theme.css"
PUBLIC_SURFACE = "public"
VERSION_QUERY_PARAMETER = "v"


class ThemeStaticAssets:
    """Resolves static files and builds stylesheet and asset URLs per theme slug."""

    def __init__(self, theme_registry: ThemeRegistry) -> None:
        self._theme_registry = theme_registry
        self._stylesheet_builder = StylesheetBuilder()

    def resolve(self, theme_slug: str, asset_path: str) -> Optional[Path]:
        """The file serving ``asset_path`` for ``theme_slug``, or None."""
        if not self._theme_registry.is_registered(theme_slug):
            return None
        for chain_slug in self._theme_registry.chain(theme_slug):
            static_directory = self._theme_registry.get(chain_slug).static_directory
            joined_path = safe_join(str(static_directory), asset_path)
            if joined_path is not None and Path(joined_path).is_file():
                return Path(joined_path)
        return None

    def asset_url(self, theme_slug: str, asset_path: str) -> str:
        url = f"{THEME_STATIC_URL_PREFIX}/{theme_slug}/{asset_path}"
        resolved_path = self.resolve(theme_slug, asset_path)
        if resolved_path is None:
            return url
        return _versioned(url, file_content_hash(resolved_path))

    def stylesheet(self, theme_slug: str) -> Stylesheet:
        descriptors_basic_first = [
            self._theme_registry.get(chain_slug)
            for chain_slug in reversed(self._theme_registry.chain(theme_slug))
        ]
        return self._stylesheet_builder.build(
            descriptors_basic_first,
            PUBLIC_SURFACE,
            self._theme_registry.contributed_stylesheet_paths(),
        )

    def stylesheet_url(self, theme_slug: str) -> str:
        return _versioned(
            THEME_STYLESHEET_PATH, self.stylesheet(theme_slug).content_hash
        )


def file_content_hash(path: Path) -> str:
    return content_hash(path.read_bytes())


def _versioned(url: str, version: str) -> str:
    return f"{url}?{VERSION_QUERY_PARAMETER}={version}"
