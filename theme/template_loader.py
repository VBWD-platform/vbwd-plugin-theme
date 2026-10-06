"""Theme template loader (S152 D1 + D8): Twig-style ``@<theme>/`` names over a theme chain.

Unqualified names resolve first-hit-wins: operator overrides
(``var/assets/theme/<active>/templates``) → each theme of the active chain →
adapter-contributed paths. ``@<slug>/<name>`` resolves only in that theme, which
lets a child template ``{% extends "@basic/x.html.j2" %}`` override the same
unqualified name and call ``{{ super() }}`` without recursing into itself.
"""
import os
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from jinja2 import BaseLoader, Environment, TemplateNotFound
from jinja2.loaders import split_template_path

from .theme_registry import ThemeRegistry

NAMESPACE_MARKER = "@"
NAMESPACE_SEPARATOR = "/"


class ThemeTemplateLoader(BaseLoader):
    """Loads templates for one active theme slug."""

    def __init__(
        self,
        theme_registry: ThemeRegistry,
        active_theme_slug: str,
        operator_templates_directory: Path,
    ) -> None:
        self._theme_registry = theme_registry
        self._active_theme_slug = active_theme_slug
        self._operator_templates_directory = operator_templates_directory

    def get_source(
        self, environment: Environment, template: str
    ) -> Tuple[str, str, Callable[[], bool]]:
        search_directories, template_name = self._search_plan(template)
        segments = split_template_path(template_name)
        for directory in search_directories:
            template_path = Path(directory, *segments)
            if template_path.is_file():
                return _read_template(template_path)
        raise TemplateNotFound(template)

    def _search_plan(self, template: str) -> Tuple[List[Path], str]:
        if template.startswith(NAMESPACE_MARKER):
            namespace, _, template_name = template[1:].partition(NAMESPACE_SEPARATOR)
            namespace_directory = self._namespace_directory(namespace)
            if namespace_directory is None or not template_name:
                raise TemplateNotFound(template)
            return [namespace_directory], template_name
        theme_directories = [
            self._theme_registry.get(slug).templates_directory
            for slug in self._theme_registry.chain(self._active_theme_slug)
        ]
        return (
            [self._operator_templates_directory]
            + theme_directories
            + self._theme_registry.contributed_template_paths()
        ), template

    def _namespace_directory(self, namespace: str) -> Optional[Path]:
        if not self._theme_registry.is_registered(namespace):
            return None
        return self._theme_registry.get(namespace).templates_directory


def _read_template(template_path: Path) -> Tuple[str, str, Callable[[], bool]]:
    source = template_path.read_text(encoding="utf-8")
    loaded_modification_time = os.path.getmtime(template_path)

    def uptodate() -> bool:
        try:
            return os.path.getmtime(template_path) == loaded_modification_time
        except OSError:
            return False

    return source, str(template_path), uptodate
