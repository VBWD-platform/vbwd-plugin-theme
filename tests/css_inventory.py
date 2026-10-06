"""S152-06c test helpers: read class names out of CSS, Vue ``<style>`` blocks,
theme templates and runtime scripts, walk ``var()`` chains and find colours
no token guards. Shared by the theme platform and its adapters' ported-CSS tests.

Deliberately small regex readers (no CSS parser dependency): selectors are the
text before each ``{`` that does not start an at-rule.
"""
import re
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
STYLE_BLOCK = re.compile(r"<style\b[^>]*>(.*?)</style>", re.DOTALL)
SELECTOR_PRELUDE = re.compile(r"([^{}]+)\{")
CLASS_IN_SELECTOR = re.compile(r"\.(-?[A-Za-z_][\w-]*)")
CLASS_ATTRIBUTE = re.compile(r'class="([^"]*)"')
JINJA_EXPRESSION = re.compile(r"\{\{.*?\}\}", re.DOTALL)
JINJA_STATEMENT = re.compile(r"\{%.*?%\}", re.DOTALL)
EXPRESSION_MARK = "\x00"
# ``{% with class_base = "term-archive" %}`` — names a template passes on.
WITH_STRING_ASSIGNMENT = re.compile(r'(\w+)\s*=\s*"([\w-]+)"')
EXPRESSION_NAME = re.compile(r"\{\{\s*(\w+)\s*\}\}")
CLASS_TOKEN = re.compile(r"[A-Za-z_][\w-]*")
# A BEM-looking string literal in a runtime script (``'cms-menu--open'``).
SCRIPT_CLASS_LITERAL = re.compile(r"'([a-z][\w-]*(?:__|--)[\w-]+)'")
DECLARATION_BLOCK = re.compile(r"\{([^{}]*)\}")
HEX_COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}\b")
FUNCTION_COLOUR = re.compile(r"\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch)\(", re.I)
NAMED_COLOURS = frozenset(
    "white black red green blue yellow orange purple pink gray grey silver "
    "maroon navy teal olive lime aqua fuchsia cyan magenta brown gold indigo "
    "violet crimson coral salmon tomato".split()
)
WORD = re.compile(r"[A-Za-z]+")
# A var() whose fallback may carry a literal colour: a --vbwd-* token, or the
# SPA's own --color-* chain the port keeps verbatim (S152-06d).
GUARDING_TOKEN_NAME = re.compile(r"^--(?:vbwd|color)-[a-z0-9-]+$")
# What resolve_fallbacks() renders for a var() without a fallback.
UNSET_TOKEN = "<unset>"


def strip_comments(css_text: str) -> str:
    return COMMENT.sub("", css_text)


def vue_style_text(vue_source: str) -> str:
    return "\n".join(STYLE_BLOCK.findall(vue_source))


def rule_classes(css_text: str) -> Set[str]:
    """Every class named in a selector of ``css_text`` (at-rule preludes skipped)."""
    classes: Set[str] = set()
    for prelude in SELECTOR_PRELUDE.findall(strip_comments(css_text)):
        selector = prelude.strip()
        if selector.startswith("@"):
            continue
        classes.update(CLASS_IN_SELECTOR.findall(selector))
    return classes


def template_class_usage(templates: Iterable[Path]) -> Tuple[Set[str], Set[str]]:
    """``(static class tokens, prefixes of interpolated tokens)`` of ``class=""``.

    * classes inside ``{% if %}…{% endif %}`` count as static (`` active``);
    * ``post-card--{{ card.mode }}`` yields the prefix ``post-card--``;
    * ``{{ class_base }}__pagination`` resolves through every
      ``{% with class_base = "…" %}`` string any template passes.
    """
    sources = [template.read_text(encoding="utf-8") for template in templates]
    assigned_values = _with_string_assignments(sources)
    static_classes: Set[str] = set()
    interpolated_prefixes: Set[str] = set()
    for source in sources:
        for attribute in CLASS_ATTRIBUTE.findall(source):
            for resolved in _resolve_leading_names(attribute, assigned_values):
                _collect_tokens(resolved, static_classes, interpolated_prefixes)
    return static_classes, interpolated_prefixes


def _with_string_assignments(sources: List[str]) -> Dict[str, Set[str]]:
    assigned_values: Dict[str, Set[str]] = {}
    for source in sources:
        for statement in JINJA_STATEMENT.findall(source):
            if statement.lstrip("{%- ").startswith("with"):
                for name, value in WITH_STRING_ASSIGNMENT.findall(statement):
                    assigned_values.setdefault(name, set()).add(value)
    return assigned_values


def _resolve_leading_names(
    attribute: str, assigned_values: Dict[str, Set[str]]
) -> List[str]:
    """``attribute`` with each ``{{ name }}`` of a with-assigned name substituted."""
    resolved = [attribute]
    for name in set(EXPRESSION_NAME.findall(attribute)) & set(assigned_values):
        pattern = re.compile(r"\{\{\s*" + name + r"\s*\}\}")
        resolved = [
            pattern.sub(value, text)
            for text in resolved
            for value in sorted(assigned_values[name])
        ]
    return resolved


def _collect_tokens(
    attribute: str, static_classes: Set[str], interpolated_prefixes: Set[str]
) -> None:
    marked = JINJA_STATEMENT.sub(" ", JINJA_EXPRESSION.sub(EXPRESSION_MARK, attribute))
    for raw_token in marked.split():
        prefix = raw_token.split(EXPRESSION_MARK, 1)[0]
        if not CLASS_TOKEN.fullmatch(prefix or "-"):
            continue
        if EXPRESSION_MARK in raw_token:
            interpolated_prefixes.add(prefix)
        else:
            static_classes.add(prefix)


def script_classes(scripts: Iterable[Path]) -> Set[str]:
    classes: Set[str] = set()
    for script in scripts:
        classes.update(SCRIPT_CLASS_LITERAL.findall(script.read_text(encoding="utf-8")))
    return classes


def is_used(class_name: str, static_classes: Set[str], prefixes: Set[str]) -> bool:
    return class_name in static_classes or any(
        class_name.startswith(prefix) and len(class_name) > len(prefix)
        for prefix in prefixes
    )


def _closing_parenthesis(value: str, open_index: int) -> int:
    depth = 0
    for index in range(open_index, len(value)):
        if value[index] == "(":
            depth += 1
        elif value[index] == ")":
            depth -= 1
            if depth == 0:
                return index
    return len(value) - 1


def _split_var_arguments(inner: str) -> Tuple[str, Optional[str]]:
    """``(name, fallback)`` of a ``var()`` body; ``fallback`` is None when absent."""
    depth = 0
    for index, character in enumerate(inner):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif character == "," and depth == 0:
            return inner[:index].strip(), inner[index + 1 :].strip()
    return inner.strip(), None


def map_var_calls(value: str, replace: Callable[[str, Optional[str]], str]) -> str:
    """``value`` with each outermost ``var(name, fallback)`` replaced by ``replace``."""
    result: List[str] = []
    index = 0
    while index < len(value):
        if value.startswith("var(", index):
            closing = _closing_parenthesis(value, index + len("var"))
            name, fallback = _split_var_arguments(value[index + len("var(") : closing])
            result.append(replace(name, fallback))
            index = closing + 1
            continue
        result.append(value[index])
        index += 1
    return "".join(result)


def var_calls(value: str) -> List[Tuple[str, Optional[str]]]:
    """Every ``(name, fallback)`` ``var()`` call in ``value``, nested fallbacks included."""
    found: List[Tuple[str, Optional[str]]] = []

    def collect(name: str, fallback: Optional[str]) -> str:
        found.append((name, fallback))
        if fallback is not None:
            found.extend(var_calls(fallback))
        return ""

    map_var_calls(value, collect)
    return found


def text_outside_token_fallbacks(value: str) -> str:
    """``value`` minus every ``var()`` name and every fallback a token guards.

    A fallback is guarded when its ``var()`` names a ``--vbwd-*`` token (themes
    override it through ``tokens.json``) or one of the SPA's own ``--color-*``
    chains (kept verbatim, S152-06d). Any other fallback stays in the text.
    """

    def replace(name: str, fallback: Optional[str]) -> str:
        if fallback is None or GUARDING_TOKEN_NAME.match(name):
            return " "
        return f" {text_outside_token_fallbacks(fallback)} "

    return map_var_calls(value, replace)


def resolve_fallbacks(value: str) -> str:
    """``value`` as rendered with no token set: each ``var()`` becomes its fallback."""

    def replace(name: str, fallback: Optional[str]) -> str:
        return UNSET_TOKEN if fallback is None else resolve_fallbacks(fallback)

    return map_var_calls(value, replace)


def declarations(css_text: str) -> List[Tuple[str, str]]:
    """``(property, value)`` of every declaration in every rule body."""
    found: List[Tuple[str, str]] = []
    for block in DECLARATION_BLOCK.findall(strip_comments(css_text)):
        for declaration in block.split(";"):
            property_name, separator, value = declaration.partition(":")
            if separator:
                found.append((property_name.strip(), value.strip()))
    return found


def hard_coded_colours(css_text: str) -> List[str]:
    """``property: value`` declarations carrying a colour no token guards.

    A literal colour is allowed ONLY as the fallback of a token
    (:func:`text_outside_token_fallbacks`). Custom-property definitions
    (``--x: …``) are checked too: a literal there is a new colour all the same.
    """
    offenders: List[str] = []
    for property_name, value in declarations(css_text):
        bare_value = text_outside_token_fallbacks(value)
        has_named_colour = any(
            word.lower() in NAMED_COLOURS for word in WORD.findall(bare_value)
        )
        if (
            HEX_COLOUR.search(bare_value)
            or FUNCTION_COLOUR.search(bare_value)
            or has_named_colour
        ):
            offenders.append(f"{property_name}: {value}")
    return offenders
