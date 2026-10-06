"""S152-06d test helpers: the ``--vbwd-<adapter>-*`` colour tokens of the theme platform
and its adapters (shared by their ported-CSS tests).

* :func:`adapter_token_fallbacks` — every adapter token an adapter's CSS uses,
  with the fallback literal(s) it carries;
* :func:`documented_colour_tokens` — the token table of the theme guide
  (``plugins/theme/docs/writing-a-theme.md`` → "Colour tokens");
* :func:`unported_spa_colours` — SPA colour declarations of used rules whose
  value the ported CSS does not render by default (coverage);
* :func:`token_fallback_mismatches` — ported token declarations whose default
  rendering differs from the SPA declaration they mirror (fallback parity).

Selectors match when the ported one equals the SPA's or scopes it
(``.cart-items-summary .plan-description`` mirrors ``.plan-description``).
"""
import re
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

import plugins.theme as theme_package
from plugins.theme.tests.css_inventory import (
    CLASS_IN_SELECTOR,
    declarations,
    hard_coded_colours,
    resolve_fallbacks,
    strip_comments,
    var_calls,
    vue_style_text,
)

COLOUR_TOKEN_DOCUMENT = (
    Path(theme_package.__file__).resolve().parent / "docs" / "writing-a-theme.md"
)
# | `--vbwd-cms-menu-overlay` | where it is used | `rgba(0,0,0,0.4)` |
DOCUMENTED_TOKEN_ROW = re.compile(
    r"^\|\s*`(--vbwd-[a-z0-9-]+)`\s*\|[^|\n]*\|\s*`([^`]+)`\s*\|\s*$", re.MULTILINE
)
RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
VUE_DEEP = re.compile(r":deep\(([^()]*)\)")
SHORT_HEX = re.compile(r"#([0-9a-f])([0-9a-f])([0-9a-f])\b")
NAMED_WHITE = re.compile(r"\bwhite\b")
SPACE_AROUND_PUNCTUATION = re.compile(r"\s*([,()])\s*")

Declaration = Tuple[str, str, str]  # (selector, property, value)


def adapter_token_prefix(adapter: str) -> str:
    return f"--vbwd-{adapter}-"


def adapter_token_fallbacks(css_text: str, adapter: str) -> Dict[str, Set[str]]:
    """``{token: {fallback, …}}`` of every ``--vbwd-<adapter>-*`` ``var()`` call."""
    prefix = adapter_token_prefix(adapter)
    tokens: Dict[str, Set[str]] = {}
    for _property_name, value in declarations(css_text):
        for name, fallback in var_calls(value):
            if name.startswith(prefix):
                tokens.setdefault(name, set()).add(fallback or "")
    return tokens


def documented_colour_tokens(adapter: str) -> Dict[str, str]:
    """``{token: SPA default}`` rows of the theme guide's token table for ``adapter``."""
    prefix = adapter_token_prefix(adapter)
    document = COLOUR_TOKEN_DOCUMENT.read_text(encoding="utf-8")
    return {
        token: default
        for token, default in DOCUMENTED_TOKEN_ROW.findall(document)
        if token.startswith(prefix)
    }


def normalised_value(value: str) -> str:
    """Case, spacing and ``white`` / ``#fff`` spellings folded for comparison."""
    compact = SPACE_AROUND_PUNCTUATION.sub(r"\1", " ".join(value.lower().split()))
    compact = NAMED_WHITE.sub("#ffffff", compact)
    return SHORT_HEX.sub(
        lambda match: "#" + "".join(digit * 2 for digit in match.groups()), compact
    )


def rendered_value(value: str) -> str:
    """The normalised value a declaration renders with no token set."""
    return normalised_value(resolve_fallbacks(value))


def _normalised_selector(selector: str) -> str:
    return " ".join(VUE_DEEP.sub(r"\1", selector).split())


def css_declarations(css_text: str) -> List[Declaration]:
    """``(selector, property, value)`` per single selector of every rule."""
    found: List[Declaration] = []
    for prelude, body in RULE.findall(strip_comments(css_text)):
        if prelude.strip().startswith("@"):
            continue
        rule_declarations = declarations("{" + body + "}")
        for selector in prelude.split(","):
            for property_name, value in rule_declarations:
                found.append((_normalised_selector(selector), property_name, value))
    return found


def _source_declarations(source_files: Iterable[Path]) -> List[Tuple[str, Declaration]]:
    found: List[Tuple[str, Declaration]] = []
    for source in source_files:
        text = source.read_text(encoding="utf-8")
        style = vue_style_text(text) if source.suffix == ".vue" else text
        found.extend((source.name, item) for item in css_declarations(style))
    return found


def _mirrors(ported_selector: str, source_selector: str) -> bool:
    return ported_selector == source_selector or ported_selector.endswith(
        " " + source_selector
    )


def _rendered_values(
    declarations_found: Iterable[Declaration], selector: str, property_name: str
) -> Set[str]:
    return {
        rendered_value(value)
        for ported_selector, ported_property, value in declarations_found
        if ported_property == property_name and _mirrors(ported_selector, selector)
    }


def unported_spa_colours(
    source_files: Iterable[Path], ported_css: str, used_classes: Set[str]
) -> List[str]:
    """``"File.vue | selector | property: value"`` of each SPA colour not rendered.

    Only SPA declarations carrying a colour no token guards, in a selector that
    names a class the adapter's templates use, are considered.
    """
    ported = css_declarations(ported_css)
    unported: List[str] = []
    for file_name, (selector, property_name, value) in _source_declarations(
        source_files
    ):
        if not set(CLASS_IN_SELECTOR.findall(selector)) & used_classes:
            continue
        if not hard_coded_colours(f"{{{property_name}: {value}}}"):
            continue
        if rendered_value(value) not in _rendered_values(
            ported, selector, property_name
        ):
            unported.append(f"{file_name} | {selector} | {property_name}: {value}")
    return unported


def token_fallback_mismatches(
    source_files: Iterable[Path], ported_css: str, adapter: str
) -> List[str]:
    """``"selector | property: value"`` of each adapter-token declaration whose
    default rendering is not the value an SPA declaration it mirrors renders."""
    prefix = adapter_token_prefix(adapter)
    source = [item for _file_name, item in _source_declarations(source_files)]
    mismatches: List[str] = []
    for selector, property_name, value in css_declarations(ported_css):
        if not any(name.startswith(prefix) for name, _ in var_calls(value)):
            continue
        spa_values = {
            rendered_value(source_value)
            for source_selector, source_property, source_value in source
            if source_property == property_name and _mirrors(selector, source_selector)
        }
        if rendered_value(value) not in spa_values:
            mismatches.append(f"{selector} | {property_name}: {value}")
    return mismatches
