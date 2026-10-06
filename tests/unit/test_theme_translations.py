"""S152-05 / D13 — UI strings: ``translations/<lang>.json`` over the template override chain.

Per key, first hit: operator ``var/assets/theme/<active>/translations`` → each
theme of the active chain → adapter-contributed paths; missing in the final
language → the policy default language → ``en`` → the key itself.
"""
import json
import os
from pathlib import Path

import pytest
from flask import Flask

from plugins.theme.theme.renderer import ThemeRenderer
from plugins.theme.theme.theme_registry import (
    BASIC_THEME_SLUG,
    ThemeDescriptor,
    ThemeRegistrationError,
    ThemeRegistry,
)
from plugins.theme.theme.translations import ThemeTranslations

TEMPLATE_NAME = "probe.html.j2"
CHILD_SLUG = "acme"


def _theme_root(tmp_path: Path, slug: str) -> Path:
    theme_root = tmp_path / "themes" / slug
    (theme_root / "templates").mkdir(parents=True)
    return theme_root


def _write_catalog(directory: Path, language: str, catalog: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    catalog_path = directory / f"{language}.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    return catalog_path


@pytest.fixture(autouse=True)
def var_directory(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("VBWD_VAR_DIR", str(tmp_path / "var"))
    return tmp_path / "var"


@pytest.fixture
def basic_root(tmp_path) -> Path:
    return _theme_root(tmp_path, BASIC_THEME_SLUG)


@pytest.fixture
def child_root(tmp_path) -> Path:
    return _theme_root(tmp_path, CHILD_SLUG)


@pytest.fixture
def contributed_directory(tmp_path) -> Path:
    directory = tmp_path / "adapter" / "translations"
    directory.mkdir(parents=True)
    return directory


def _registry(basic_root: Path, child_root: Path, contributed: Path) -> ThemeRegistry:
    registry = ThemeRegistry()
    registry.register(ThemeDescriptor(BASIC_THEME_SLUG, "Basic", None, basic_root))
    registry.register(ThemeDescriptor(CHILD_SLUG, "Acme", BASIC_THEME_SLUG, child_root))
    registry.add_contributed_translation_path(contributed)
    return registry


@pytest.fixture
def chain_directories(var_directory, basic_root, child_root, contributed_directory):
    """``(operator, child, basic, contributed)`` translation directories for acme."""
    operator_directory = (
        var_directory / "assets" / "theme" / CHILD_SLUG / "translations"
    )
    return (
        operator_directory,
        child_root / "translations",
        basic_root / "translations",
        contributed_directory,
    )


@pytest.fixture
def translations(basic_root, child_root, contributed_directory) -> ThemeTranslations:
    return ThemeTranslations(_registry(basic_root, child_root, contributed_directory))


@pytest.mark.parametrize(
    "present_in, expected",
    [
        ((0, 1, 2, 3), "operator"),
        ((1, 2, 3), "child"),
        ((2, 3), "basic"),
        ((3,), "contributed"),
    ],
)
def test_first_hit_wins_operator_child_basic_contributed(
    translations, chain_directories, present_in, expected
):
    names = ("operator", "child", "basic", "contributed")
    for directory_index in present_in:
        _write_catalog(
            chain_directories[directory_index],
            "de",
            {"Log in": names[directory_index]},
        )

    assert translations.translate(CHILD_SLUG, "Log in", ("de",)) == expected


def test_a_child_catalog_overrides_basic_key_by_key(translations, chain_directories):
    _operator, child_directory, basic_directory, _contributed = chain_directories
    _write_catalog(basic_directory, "de", {"Log in": "Anmelden", "Cart": "Warenkorb"})
    _write_catalog(child_directory, "de", {"Log in": "Einloggen"})

    assert translations.translate(CHILD_SLUG, "Log in", ("de",)) == "Einloggen"
    assert translations.translate(CHILD_SLUG, "Cart", ("de",)) == "Warenkorb"


def test_missing_key_falls_back_final_then_default_then_en_then_key(
    translations, chain_directories
):
    _operator, _child, basic_directory, contributed_directory = chain_directories
    _write_catalog(basic_directory, "fr", {"only_default": "défaut"})
    _write_catalog(contributed_directory, "en", {"only_en": "english"})
    _write_catalog(basic_directory, "de", {"in_final": "final"})
    languages = ("de", "fr", "en")

    assert translations.translate(CHILD_SLUG, "in_final", languages) == "final"
    assert translations.translate(CHILD_SLUG, "only_default", languages) == "défaut"
    assert translations.translate(CHILD_SLUG, "only_en", languages) == "english"
    assert translations.translate(CHILD_SLUG, "nowhere", languages) == "nowhere"


def test_the_final_language_anywhere_in_the_chain_beats_the_default_language(
    translations, chain_directories
):
    operator_directory, _child, _basic, contributed_directory = chain_directories
    _write_catalog(operator_directory, "fr", {"Log in": "Connexion"})
    _write_catalog(contributed_directory, "de", {"Log in": "Anmelden"})

    assert translations.translate(CHILD_SLUG, "Log in", ("de", "fr")) == "Anmelden"


def test_catalogs_are_cached_until_the_file_changes(translations, chain_directories):
    catalog_path = _write_catalog(chain_directories[2], "de", {"Log in": "v1"})
    assert translations.translate(CHILD_SLUG, "Log in", ("de",)) == "v1"

    catalog_path.write_text(json.dumps({"Log in": "v2"}), encoding="utf-8")
    modification_time = catalog_path.stat().st_mtime + 5
    os.utime(catalog_path, (modification_time, modification_time))

    assert translations.translate(CHILD_SLUG, "Log in", ("de",)) == "v2"


def test_an_unreadable_operator_catalog_is_skipped_with_a_warning(
    translations, chain_directories, caplog
):
    operator_directory, _child, basic_directory, _contributed = chain_directories
    operator_directory.mkdir(parents=True)
    (operator_directory / "de.json").write_text("{not json", encoding="utf-8")
    _write_catalog(basic_directory, "de", {"Log in": "Anmelden"})

    assert translations.translate(CHILD_SLUG, "Log in", ("de",)) == "Anmelden"
    assert any("de.json" in record.getMessage() for record in caplog.records)


def test_a_contributed_translation_path_with_a_broken_catalog_is_refused(tmp_path):
    broken_directory = tmp_path / "broken"
    _write_catalog(broken_directory, "en", {"count": 3})

    with pytest.raises(ThemeRegistrationError):
        ThemeRegistry().add_contributed_translation_path(broken_directory)


# ── the template global ─────────────────────────────────────────────────────


def _render(registry: ThemeRegistry, template_source: str, context: dict) -> str:
    templates_directory = registry.get(CHILD_SLUG).templates_directory
    (templates_directory / TEMPLATE_NAME).write_text(template_source, encoding="utf-8")
    app = Flask(__name__)
    app.testing = True
    with app.app_context():
        return ThemeRenderer(registry, lambda: CHILD_SLUG).render(
            TEMPLATE_NAME, context
        )


@pytest.fixture
def registry(basic_root, child_root, contributed_directory) -> ThemeRegistry:
    return _registry(basic_root, child_root, contributed_directory)


def test_gettext_global_translates_into_the_context_language(registry, basic_root):
    _write_catalog(basic_root / "translations", "de", {"Log in": "Anmelden"})

    html = _render(
        registry,
        "{{ _('Log in') }}|{{ gettext('Log in') }}",
        {"language": "de", "default_language": "en"},
    )

    assert html == "Anmelden|Anmelden"


def test_gettext_falls_back_to_the_context_default_language(registry, basic_root):
    _write_catalog(basic_root / "translations", "fr", {"Log in": "Connexion"})

    html = _render(
        registry, "{{ _('Log in') }}", {"language": "de", "default_language": "fr"}
    )

    assert html == "Connexion"


def test_gettext_without_a_language_in_the_context_uses_en(registry, basic_root):
    _write_catalog(basic_root / "translations", "en", {"greeting": "Hello"})

    assert _render(registry, "{{ _('greeting') }}", {}) == "Hello"


def test_gettext_translates_inside_an_imported_macro(registry, basic_root):
    _write_catalog(basic_root / "translations", "de", {"Log in": "Anmelden"})
    macros_path = registry.get(CHILD_SLUG).templates_directory / "macros.html.j2"
    macros_path.write_text(
        "{% macro login() %}{{ _('Log in') }}{% endmacro %}", encoding="utf-8"
    )

    html = _render(
        registry,
        "{% import 'macros.html.j2' as macros %}{{ macros.login() }}",
        {"language": "de", "default_language": "en"},
    )

    assert html == "Anmelden"


def test_params_are_interpolated_and_escaped(registry, basic_root):
    _write_catalog(
        basic_root / "translations", "de", {"Hello %(name)s": "Hallo <%(name)s>"}
    )

    html = _render(
        registry,
        "{{ _('Hello %(name)s', name=visitor) }}",
        {"language": "de", "default_language": "en", "visitor": "<b>Ada</b>"},
    )

    assert html == "Hallo &lt;&lt;b&gt;Ada&lt;/b&gt;&gt;"


def test_a_catalog_string_is_plain_text_never_markup(registry, basic_root):
    _write_catalog(basic_root / "translations", "en", {"tagline": "<script>x</script>"})

    assert _render(registry, "{{ _('tagline') }}", {}) == (
        "&lt;script&gt;x&lt;/script&gt;"
    )


def test_a_message_with_a_broken_placeholder_renders_unformatted(
    registry, basic_root, caplog
):
    _write_catalog(basic_root / "translations", "en", {"Hi": "Hi %(missing)s"})

    html = _render(registry, "{{ _('Hi', name='Ada') }}", {})

    assert html == "Hi %(missing)s"
    assert any("Hi" in record.getMessage() for record in caplog.records)
