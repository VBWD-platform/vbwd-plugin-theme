"""UI-string catalogs for themed pages (S152-05 / D13).

A catalog is ``translations/<language>.json``: a JSON object of message → text.
Per message, the first hit wins, in the same order as templates (D8):
operator overrides ``var/assets/theme/<active>/translations`` → each theme of
the active chain → adapter-contributed paths. The languages are tried in the
order given (final → policy default → ``en``); a message found nowhere is
returned as is.

Parameters use ``%(name)s`` placeholders (never ``str.format``, whose
attribute lookups would reach past the sandbox). The result is a plain
``str``: autoescape escapes both the catalog text and the parameters.
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from vbwd.services.asset_storage import asset_dir

from .theme_registry import THEME_ASSET_OWNER, TRANSLATIONS_DIRECTORY, ThemeRegistry

logger = logging.getLogger(__name__)

CATALOG_SUFFIX = ".json"

Catalog = Mapping[str, str]


class ThemeTranslations:
    """Looks messages up along the active theme's catalog chain; caches files by mtime."""

    def __init__(self, theme_registry: ThemeRegistry) -> None:
        self._theme_registry = theme_registry
        self._catalogs_by_path: Dict[Path, Tuple[float, Catalog]] = {}

    def translate(
        self,
        theme_slug: str,
        message: str,
        languages: Sequence[str],
        params: Optional[Mapping[str, Any]] = None,
    ) -> str:
        """``message`` in the first of ``languages`` that has it, with ``params`` applied."""
        translated = self._lookup(theme_slug, message, languages)
        if not params:
            return translated
        try:
            return translated % dict(params)
        except (KeyError, TypeError, ValueError) as error:
            logger.warning(
                "theme: translation '%s' does not fit its params: %s", translated, error
            )
            return translated

    def _lookup(self, theme_slug: str, message: str, languages: Sequence[str]) -> str:
        directories = self._catalog_directories(theme_slug)
        for language in languages:
            for directory in directories:
                catalog = self._catalog(directory / f"{language}{CATALOG_SUFFIX}")
                if message in catalog:
                    return catalog[message]
        return message

    def _catalog_directories(self, theme_slug: str) -> List[Path]:
        operator_directory = Path(
            asset_dir(THEME_ASSET_OWNER, theme_slug, TRANSLATIONS_DIRECTORY)
        )
        theme_directories = [
            self._theme_registry.get(slug).root / TRANSLATIONS_DIRECTORY
            for slug in self._theme_registry.chain(theme_slug)
        ]
        return (
            [operator_directory]
            + theme_directories
            + self._theme_registry.contributed_translation_paths()
        )

    def _catalog(self, catalog_path: Path) -> Catalog:
        try:
            modification_time = catalog_path.stat().st_mtime
        except OSError:
            return {}
        cached = self._catalogs_by_path.get(catalog_path)
        if cached is not None and cached[0] == modification_time:
            return cached[1]
        catalog = _read_catalog(catalog_path)
        self._catalogs_by_path[catalog_path] = (modification_time, catalog)
        return catalog


def _read_catalog(catalog_path: Path) -> Catalog:
    """The catalog's string entries; an unreadable file (operator typo) counts as empty."""
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        logger.warning("theme: skipping unreadable catalog %s: %s", catalog_path, error)
        return {}
    if not isinstance(catalog, dict):
        logger.warning("theme: skipping %s, not a JSON object", catalog_path)
        return {}
    return {
        message: text
        for message, text in catalog.items()
        if isinstance(message, str) and isinstance(text, str)
    }
