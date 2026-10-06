"""S152-05b — the shape every non-English theme catalog must keep.

Shared by the theme plugin and its adapters' tests: a ``<language>.json`` next
to ``en.json`` only translates messages ``en.json`` has, holds strings only,
uses the theme's ``%(name)s`` parameters (never vue-i18n ``{name}``), and asks
for exactly the parameters its English message asks for.
"""
import json
import re
from pathlib import Path
from typing import Dict, List

ENGLISH_CATALOG = "en.json"
THEME_PARAMETER = re.compile(r"%\((\w+)\)s")
VUE_PLACEHOLDER = re.compile(r"\{\s*\w+\s*\}")


def _read(catalog_path: Path) -> Dict[str, object]:
    return json.loads(catalog_path.read_text(encoding="utf-8"))


def translated_catalog_paths(translations_directory: Path) -> List[Path]:
    """Every ``<language>.json`` in the directory except ``en.json``."""
    return sorted(
        path
        for path in translations_directory.glob("*.json")
        if path.name != ENGLISH_CATALOG
    )


def _message_violations(language: str, message: str, text: object, english: str):
    if not isinstance(text, str):
        return [f"{language}: {message} is not a string"]
    violations = []
    if VUE_PLACEHOLDER.search(text):
        violations.append(f"{language}: {message} keeps a vue placeholder: {text!r}")
    if set(THEME_PARAMETER.findall(text)) != set(THEME_PARAMETER.findall(english)):
        violations.append(f"{language}: {message} params differ from en: {text!r}")
    return violations


def catalog_contract_violations(translations_directory: Path) -> List[str]:
    """What breaks the contract, as readable lines; empty when every catalog keeps it."""
    english = _read(translations_directory / ENGLISH_CATALOG)
    violations: List[str] = []
    for catalog_path in translated_catalog_paths(translations_directory):
        language = catalog_path.stem
        for message, text in _read(catalog_path).items():
            if message not in english:
                violations.append(f"{language}: {message} is not in en.json")
                continue
            violations.extend(
                _message_violations(language, message, text, str(english[message]))
            )
    return violations
