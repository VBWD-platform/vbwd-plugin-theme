"""S152-05b — the catalog contract catches each way a translated catalog can break."""
import json

from plugins.theme.tests.catalog_contract import (
    catalog_contract_violations,
    translated_catalog_paths,
)
from plugins.theme.theme.theme_registry import (
    BASIC_THEME_DESCRIPTOR,
    TRANSLATIONS_DIRECTORY,
)

ENGLISH = {"greeting": "Hello %(name)s", "plain": "Save"}


def _write_catalogs(directory, german):
    (directory / "en.json").write_text(json.dumps(ENGLISH), encoding="utf-8")
    (directory / "de.json").write_text(json.dumps(german), encoding="utf-8")
    return directory


def test_a_faithful_translation_keeps_the_contract(tmp_path):
    directory = _write_catalogs(tmp_path, {"greeting": "Hallo %(name)s"})

    assert catalog_contract_violations(directory) == []


def test_a_message_english_lacks_breaks_it(tmp_path):
    directory = _write_catalogs(tmp_path, {"extra": "Extra"})

    assert catalog_contract_violations(directory) == ["de: extra is not in en.json"]


def test_a_non_string_value_breaks_it(tmp_path):
    directory = _write_catalogs(tmp_path, {"plain": ["Speichern"]})

    assert catalog_contract_violations(directory) == ["de: plain is not a string"]


def test_a_vue_placeholder_breaks_it(tmp_path):
    directory = _write_catalogs(tmp_path, {"greeting": "Hallo {name}"})

    violations = catalog_contract_violations(directory)

    assert any("vue placeholder" in violation for violation in violations)


def test_a_different_parameter_set_breaks_it(tmp_path):
    directory = _write_catalogs(tmp_path, {"greeting": "Hallo %(user)s"})

    assert catalog_contract_violations(directory) == [
        "de: greeting params differ from en: 'Hallo %(user)s'"
    ]


def test_english_itself_is_not_a_translated_catalog(tmp_path):
    directory = _write_catalogs(tmp_path, {})

    assert [path.name for path in translated_catalog_paths(directory)] == ["de.json"]


def test_the_basic_theme_catalogs_keep_the_contract():
    translations = BASIC_THEME_DESCRIPTOR.root / TRANSLATIONS_DIRECTORY

    assert catalog_contract_violations(translations) == []
    assert (translations / "de.json").is_file()
