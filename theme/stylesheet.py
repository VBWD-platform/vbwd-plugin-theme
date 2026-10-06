"""Theme stylesheet (S152 D8): the CSS chain plus one merged ``:root`` token block.

Pure: descriptors and a surface in, CSS text and its content hash out. For each
stylesheet directory it concatenates ``_shared/*.css`` and then
``<surface>/*.css`` (sorted by file name). The order is:

1. the basic theme (the root of every chain),
2. the stylesheet directories adapters contribute, in registration order
   (structural CSS of the SPA components an adapter mirrors),
3. the child themes, parent before child — so a child theme overrides both,
4. one ``:root { … }`` block of the merged ``tokens.json`` values. A child's
   token wins and every token is emitted once, sorted by name.

The page's own CMS styles are linked after this stylesheet and keep the final say.
"""
import hashlib
import json
from pathlib import Path
from typing import Dict, List, NamedTuple, Sequence

from .theme_registry import ThemeDescriptor

SHARED_STATIC_DIRECTORY = "_shared"
CSS_FILE_PATTERN = "*.css"
CONTENT_HASH_LENGTH = 16


def content_hash(content: bytes) -> str:
    """The cache-busting version of an asset: sha256, first 16 hex digits."""
    return hashlib.sha256(content).hexdigest()[:CONTENT_HASH_LENGTH]


class Stylesheet(NamedTuple):
    css_text: str
    content_hash: str


class StylesheetBuilder:
    """Builds the stylesheet of a theme chain for one surface."""

    def build(
        self,
        descriptors_basic_first: Sequence[ThemeDescriptor],
        surface: str,
        contributed_stylesheet_paths: Sequence[Path] = (),
    ) -> Stylesheet:
        basic_descriptor, *child_descriptors = descriptors_basic_first
        stylesheet_directories = [
            basic_descriptor.static_directory,
            *contributed_stylesheet_paths,
            *(descriptor.static_directory for descriptor in child_descriptors),
        ]
        css_parts: List[str] = []
        for stylesheet_directory in stylesheet_directories:
            for directory_name in (SHARED_STATIC_DIRECTORY, surface):
                css_parts.extend(_css_files_text(stylesheet_directory / directory_name))
        merged_tokens: Dict[str, str] = {}
        for descriptor in descriptors_basic_first:
            merged_tokens.update(_read_tokens(descriptor))
        css_parts.append(_root_token_block(merged_tokens))
        css_text = "\n".join(css_parts)
        return Stylesheet(css_text, content_hash(css_text.encode("utf-8")))


def _css_files_text(directory: Path) -> List[str]:
    if not directory.is_dir():
        return []
    css_paths = sorted(directory.glob(CSS_FILE_PATTERN), key=lambda path: path.name)
    return [_read_text(path) for path in css_paths if path.is_file()]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_tokens(descriptor: ThemeDescriptor) -> Dict[str, str]:
    """Tokens were validated at registration (``ThemeRegistry.register``)."""
    if not descriptor.tokens_path.is_file():
        return {}
    return json.loads(_read_text(descriptor.tokens_path))


def _root_token_block(tokens: Dict[str, str]) -> str:
    declarations = "".join(
        f"  {token_name}: {tokens[token_name]};\n" for token_name in sorted(tokens)
    )
    return f":root {{\n{declarations}}}\n"
