"""Write the theme's non-English UI catalogs from the fe-user locales (S152-05b).

The theme ``en.json`` catalogs were seeded from the SPA's English, key for key.
For every catalog below this script finds, per message, the fe-user source the
English came from (the first source, in priority order, whose English converts
to the catalog's English), then copies that source's translation into
``translations/<language>.json`` for every language the sources provide.

Theme-only messages (no SPA source) and messages a language lacks are left out:
the runtime falls back final → default → ``en`` → key. Values whose vue-i18n
syntax has no theme equivalent (plurals, linked or literal messages) or whose
parameters differ from the English are left out too, and reported.

Stdlib only; deterministic output. Run from anywhere::

    python3 plugins/theme/bin/sync_translations_from_fe_user.py [--fe-user PATH]
"""
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, Iterator, List, NamedTuple, Optional, Sequence, Tuple

PLUGINS_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FE_USER_ROOT = PLUGINS_ROOT.parents[1] / "vbwd-fe-user"
ENGLISH = "en"
CATALOG_SUFFIX = ".json"
JSON_INDENT = 2
CORE_LOCALES = "vue/src/i18n/locales"
VUE_PARAMETER = re.compile(r"\{(\w+)\}")
THEME_PARAMETER = re.compile(r"%\((\w+)\)s")
# vue-i18n syntax with no ``%(name)s`` equivalent: leftover braces, plurals, links.
UNSUPPORTED_SYNTAX = re.compile(r"[{}|]|@:")


def _plugin_locales(fe_user_plugin: str) -> str:
    return f"plugins/{fe_user_plugin}/locales"


class Adapter(NamedTuple):
    """A theme catalog directory and its fe-user locale directories, highest priority first."""

    name: str
    translations_directory: str
    source_locales: Tuple[str, ...]


ADAPTERS = (
    Adapter("theme", "theme/theme/themes/basic/translations", (CORE_LOCALES,)),
    Adapter(
        "theme_cms",
        "theme_cms/theme_cms/translations",
        (_plugin_locales("cms"), _plugin_locales("landing1"), CORE_LOCALES),
    ),
    Adapter(
        "theme_checkout",
        "theme_checkout/theme_checkout/translations",
        (
            _plugin_locales("checkout"),
            CORE_LOCALES,
            # The payment flows' pages share theme_checkout's catalogs (layout B).
            _plugin_locales("stripe-payment"),
            _plugin_locales("paypal-payment"),
        ),
    ),
    Adapter(
        "theme_dataset",
        "theme_dataset/theme_dataset/translations",
        (_plugin_locales("dataset"),),
    ),
    Adapter(
        "theme_subscription",
        "theme_subscription/theme_subscription/translations",
        (_plugin_locales("subscription"), CORE_LOCALES),
    ),
    Adapter(
        "theme_booking",
        "theme_booking/theme_booking/translations",
        (_plugin_locales("booking"), CORE_LOCALES),
    ),
)

Messages = Dict[str, str]


def _flatten(prefix: str, node: dict) -> Iterator[Tuple[str, object]]:
    for key, value in node.items():
        if isinstance(value, dict):
            yield from _flatten(f"{prefix}{key}.", value)
        else:
            yield f"{prefix}{key}", value


def _read_messages(catalog_path: Path) -> Dict[str, object]:
    if not catalog_path.is_file():
        return {}
    return dict(_flatten("", json.loads(catalog_path.read_text(encoding="utf-8"))))


def to_theme_message(spa_text: object, escape_percent: bool) -> Optional[str]:
    """``{name}`` → ``%(name)s`` (and ``%`` → ``%%`` when the message is formatted)."""
    if not isinstance(spa_text, str):
        return None
    text = spa_text.replace("%", "%%") if escape_percent else spa_text
    converted = VUE_PARAMETER.sub(r"%(\1)s", text)
    return None if UNSUPPORTED_SYNTAX.search(converted) else converted


def _source_of(
    message: str, english_text: str, english_sources: Sequence[Dict[str, object]]
) -> Optional[int]:
    escape_percent = bool(THEME_PARAMETER.search(english_text))
    for index, source in enumerate(english_sources):
        if to_theme_message(source.get(message), escape_percent) == english_text:
            return index
    return None


def _languages(fe_user_root: Path, adapter: Adapter) -> List[str]:
    languages = {
        path.stem
        for locales in adapter.source_locales
        for path in (fe_user_root / locales).glob(f"*{CATALOG_SUFFIX}")
    }
    return sorted(languages - {ENGLISH})


def _translate(
    english: Messages, origins: Dict[str, int], sources: Sequence[Dict[str, object]]
) -> Tuple[Messages, List[str]]:
    translated: Messages = {}
    skipped: List[str] = []
    for message, origin in origins.items():
        if message not in sources[origin]:
            continue
        english_parameters = set(THEME_PARAMETER.findall(english[message]))
        text = to_theme_message(sources[origin][message], bool(english_parameters))
        if text is None or set(THEME_PARAMETER.findall(text)) != english_parameters:
            skipped.append(message)
            continue
        translated[message] = text
    return translated, skipped


def build_catalogs(
    fe_user_root: Path, adapter: Adapter
) -> Tuple[Dict[str, Messages], Dict[str, List[str]]]:
    """Per language: the translated catalog, and the messages left out as unconvertible."""
    english_path = PLUGINS_ROOT / adapter.translations_directory / "en.json"
    english: Messages = json.loads(english_path.read_text(encoding="utf-8"))
    english_sources = [
        _read_messages(fe_user_root / locales / f"{ENGLISH}{CATALOG_SUFFIX}")
        for locales in adapter.source_locales
    ]
    origins = {}
    for message, text in english.items():
        origin = _source_of(message, text, english_sources)
        if origin is not None:
            origins[message] = origin
    catalogs, skipped = {}, {}
    for language in _languages(fe_user_root, adapter):
        sources = [
            _read_messages(fe_user_root / locales / f"{language}{CATALOG_SUFFIX}")
            for locales in adapter.source_locales
        ]
        catalogs[language], skipped[language] = _translate(english, origins, sources)
    return catalogs, skipped


def _write_catalog(catalog_path: Path, catalog: Messages) -> None:
    text = json.dumps(catalog, ensure_ascii=False, indent=JSON_INDENT, sort_keys=True)
    catalog_path.write_text(text + "\n", encoding="utf-8")


def sync(fe_user_root: Path) -> None:
    """Write every adapter's catalogs and print a key count per language."""
    for adapter in ADAPTERS:
        catalogs, skipped = build_catalogs(fe_user_root, adapter)
        directory = PLUGINS_ROOT / adapter.translations_directory
        for language, catalog in catalogs.items():
            if catalog:
                _write_catalog(directory / f"{language}{CATALOG_SUFFIX}", catalog)
        counts = " ".join(f"{lang}={len(cat)}" for lang, cat in catalogs.items())
        print(f"{adapter.name}: {counts}")
        for language, messages in skipped.items():
            if messages:
                print(f"  {language} left out (unconvertible): {sorted(messages)}")


def main(arguments: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fe-user", type=Path, default=DEFAULT_FE_USER_ROOT)
    fe_user_root = parser.parse_args(arguments).fe_user
    if not (fe_user_root / CORE_LOCALES).is_dir():
        print(f"fe-user locales not found under {fe_user_root}", file=sys.stderr)
        return 1
    sync(fe_user_root)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
