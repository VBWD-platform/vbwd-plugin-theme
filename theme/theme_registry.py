"""Theme registry (S152-02, "The extension contract"): the seam child themes register into.

A child-theme plugin registers a :class:`ThemeDescriptor` from its ``on_enable``.
``register()`` validates the descriptor up front so a broken theme fails at boot
with a clear message instead of rendering a broken page later.
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .page_registry import resolve_theme_plugin

BASIC_THEME_SLUG = "basic"
# ``asset_dir`` owner of the operator overrides (``var/assets/theme/<slug>/…``).
THEME_ASSET_OWNER = "theme"
TEMPLATES_DIRECTORY = "templates"
STATIC_DIRECTORY = "static"
TOKENS_FILE = "tokens.json"
TRANSLATIONS_DIRECTORY = "translations"

THEME_SLUG_PATTERN = re.compile(r"^[a-z0-9_-]+$")
TOKEN_NAME_PATTERN = re.compile(r"^--vbwd-[a-z0-9-]+$")
FORBIDDEN_TOKEN_VALUE_CHARACTERS = frozenset(";{}<>")


class ThemeRegistrationError(ValueError):
    """A theme descriptor the registry refuses."""


@dataclass(frozen=True)
class ThemeDescriptor:
    """One theme: ``root`` holds ``templates/`` and optional static/translations/tokens."""

    slug: str
    name: str
    parent: Optional[str]
    root: Path

    @property
    def templates_directory(self) -> Path:
        return self.root / TEMPLATES_DIRECTORY

    @property
    def static_directory(self) -> Path:
        return self.root / STATIC_DIRECTORY

    @property
    def tokens_path(self) -> Path:
        return self.root / TOKENS_FILE


def _read_json_file(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ThemeRegistrationError(f"{path} is not readable JSON: {error}") from None


def _validate_tokens(slug: str, tokens_path: Path) -> None:
    tokens = _read_json_file(tokens_path)
    if not isinstance(tokens, dict):
        raise ThemeRegistrationError(
            f"theme '{slug}': {TOKENS_FILE} must be a JSON object"
        )
    for token_name, token_value in tokens.items():
        if not TOKEN_NAME_PATTERN.match(token_name):
            raise ThemeRegistrationError(
                f"theme '{slug}': token name '{token_name}' must match "
                f"{TOKEN_NAME_PATTERN.pattern}"
            )
        if not isinstance(token_value, str) or FORBIDDEN_TOKEN_VALUE_CHARACTERS & set(
            token_value
        ):
            raise ThemeRegistrationError(
                f"theme '{slug}': token value of '{token_name}' must be a string "
                "without any of ; { } < >"
            )


def _validate_translations(slug: str, translations_directory: Path) -> None:
    for translation_path in sorted(translations_directory.glob("*.json")):
        try:
            catalog = _read_json_file(translation_path)
        except ThemeRegistrationError as error:
            raise ThemeRegistrationError(f"theme '{slug}': {error}") from None
        is_string_map = isinstance(catalog, dict) and all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in catalog.items()
        )
        if not is_string_map:
            raise ThemeRegistrationError(
                f"theme '{slug}': {translation_path.name} must be a JSON object "
                "of string to string"
            )


class ThemeRegistry:
    """Registered themes plus the template, translation and stylesheet paths adapters contribute."""

    def __init__(self) -> None:
        self._themes_by_slug: Dict[str, ThemeDescriptor] = {}
        self._contributed_template_paths: List[Path] = []
        self._contributed_translation_paths: List[Path] = []
        self._contributed_stylesheet_paths: List[Path] = []

    def register(self, descriptor: ThemeDescriptor) -> None:
        self._validate_identity(descriptor)
        self._validate_parent(descriptor)
        self._validate_files(descriptor)
        self._themes_by_slug[descriptor.slug] = descriptor

    def is_registered(self, slug: str) -> bool:
        return slug in self._themes_by_slug

    def get(self, slug: str) -> ThemeDescriptor:
        return self._themes_by_slug[slug]

    def chain(self, slug: str) -> List[str]:
        """``[slug, parent, …, "basic"]`` — the template resolution order."""
        chain: List[str] = []
        current_slug: Optional[str] = slug
        while current_slug is not None:
            chain.append(current_slug)
            current_slug = self._themes_by_slug[current_slug].parent
        return chain

    def add_contributed_template_path(self, path: Path) -> None:
        """Adapters add their templates here; they rank below every theme."""
        self._contributed_template_paths.append(path)

    def contributed_template_paths(self) -> List[Path]:
        return list(self._contributed_template_paths)

    def add_contributed_translation_path(self, path: Path) -> None:
        """Adapters add their ``<language>.json`` catalogs here; they rank below every theme."""
        _validate_translations(f"contributed {path}", path)
        self._contributed_translation_paths.append(path)

    def contributed_translation_paths(self) -> List[Path]:
        return list(self._contributed_translation_paths)

    def add_contributed_stylesheet_path(self, path: Path) -> None:
        """Adapters add a ``_shared/`` + ``<surface>/`` CSS directory here.

        It is concatenated after the basic theme and before every child theme
        (``StylesheetBuilder``), so a child theme can override it.
        """
        if not path.is_dir():
            raise ThemeRegistrationError(
                f"contributed stylesheet path {path} is not a directory"
            )
        self._contributed_stylesheet_paths.append(path)

    def contributed_stylesheet_paths(self) -> List[Path]:
        return list(self._contributed_stylesheet_paths)

    def _validate_identity(self, descriptor: ThemeDescriptor) -> None:
        if not THEME_SLUG_PATTERN.match(descriptor.slug):
            raise ThemeRegistrationError(
                f"theme slug '{descriptor.slug}' must match {THEME_SLUG_PATTERN.pattern}"
            )
        if descriptor.slug in self._themes_by_slug:
            raise ThemeRegistrationError(
                f"theme '{descriptor.slug}' is already registered"
            )

    def _validate_parent(self, descriptor: ThemeDescriptor) -> None:
        if descriptor.slug == BASIC_THEME_SLUG:
            if descriptor.parent is not None:
                raise ThemeRegistrationError(
                    f"theme '{BASIC_THEME_SLUG}' has no parent"
                )
            return
        if descriptor.parent is None:
            raise ThemeRegistrationError(
                f"theme '{descriptor.slug}' needs a parent (at least '{BASIC_THEME_SLUG}')"
            )
        if descriptor.parent == descriptor.slug:
            raise ThemeRegistrationError(
                f"theme '{descriptor.slug}' would form a cycle: it is its own parent"
            )
        if descriptor.parent not in self._themes_by_slug:
            raise ThemeRegistrationError(
                f"theme '{descriptor.slug}' has unknown parent '{descriptor.parent}'"
            )

    @staticmethod
    def _validate_files(descriptor: ThemeDescriptor) -> None:
        if not descriptor.templates_directory.is_dir():
            raise ThemeRegistrationError(
                f"theme '{descriptor.slug}': {descriptor.templates_directory} "
                f"is not a {TEMPLATES_DIRECTORY} directory"
            )
        if descriptor.tokens_path.is_file():
            _validate_tokens(descriptor.slug, descriptor.tokens_path)
        translations_directory = descriptor.root / TRANSLATIONS_DIRECTORY
        if translations_directory.is_dir():
            _validate_translations(descriptor.slug, translations_directory)


BASIC_THEME_DESCRIPTOR = ThemeDescriptor(
    slug=BASIC_THEME_SLUG,
    name="Basic",
    parent=None,
    root=Path(__file__).resolve().parent / "themes" / BASIC_THEME_SLUG,
)


def resolve_theme_registry() -> ThemeRegistry:
    """The theme registry of the running app's theme plugin (child themes call this)."""
    return resolve_theme_plugin().theme_registry
