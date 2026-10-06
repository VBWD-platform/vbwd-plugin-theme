"""S152-02 — ThemeRegistry validates child-theme descriptors on register()."""
import json
from pathlib import Path
from typing import Optional

import pytest

from plugins.theme.theme.theme_registry import (
    BASIC_THEME_SLUG,
    ThemeDescriptor,
    ThemeRegistrationError,
    ThemeRegistry,
)


def _theme_root(base_directory: Path, slug: str) -> Path:
    root = base_directory / slug
    (root / "templates").mkdir(parents=True)
    return root


def _descriptor(root: Path, slug: str, parent: Optional[str] = BASIC_THEME_SLUG):
    return ThemeDescriptor(slug=slug, name=slug.title(), parent=parent, root=root)


@pytest.fixture
def registry(tmp_path) -> ThemeRegistry:
    theme_registry = ThemeRegistry()
    theme_registry.register(
        _descriptor(_theme_root(tmp_path, "basic"), BASIC_THEME_SLUG, parent=None)
    )
    return theme_registry


def test_chain_walks_child_to_basic(registry, tmp_path):
    registry.register(_descriptor(_theme_root(tmp_path, "acme"), "acme"))
    registry.register(
        _descriptor(_theme_root(tmp_path, "acme_dark"), "acme_dark", "acme")
    )

    assert registry.chain("acme_dark") == ["acme_dark", "acme", "basic"]
    assert registry.chain("basic") == ["basic"]


def test_unknown_parent_is_refused(registry, tmp_path):
    with pytest.raises(ThemeRegistrationError, match="unknown parent 'missing'"):
        registry.register(_descriptor(_theme_root(tmp_path, "acme"), "acme", "missing"))


def test_a_theme_cannot_be_its_own_parent(registry, tmp_path):
    with pytest.raises(ThemeRegistrationError, match="cycle"):
        registry.register(_descriptor(_theme_root(tmp_path, "acme"), "acme", "acme"))


def test_two_registrations_pointing_at_each_other_never_form_a_cycle(
    registry, tmp_path
):
    first_root = _theme_root(tmp_path, "first")
    second_root = _theme_root(tmp_path, "second")

    with pytest.raises(ThemeRegistrationError, match="unknown parent 'second'"):
        registry.register(_descriptor(first_root, "first", "second"))
    with pytest.raises(ThemeRegistrationError, match="unknown parent 'first'"):
        registry.register(_descriptor(second_root, "second", "first"))

    assert not registry.is_registered("first")
    assert not registry.is_registered("second")


def test_duplicate_slug_is_refused(registry, tmp_path):
    registry.register(_descriptor(_theme_root(tmp_path, "acme"), "acme"))

    with pytest.raises(ThemeRegistrationError, match="already registered"):
        registry.register(_descriptor(_theme_root(tmp_path, "acme_copy"), "acme"))


@pytest.mark.parametrize("bad_slug", ["Acme", "acme theme", "acme/x", "", "ac.me"])
def test_bad_slug_is_refused(registry, tmp_path, bad_slug):
    with pytest.raises(ThemeRegistrationError, match="slug"):
        registry.register(_descriptor(_theme_root(tmp_path, "root"), bad_slug))


def test_only_basic_may_have_no_parent(registry, tmp_path):
    with pytest.raises(ThemeRegistrationError, match="parent"):
        registry.register(
            _descriptor(_theme_root(tmp_path, "acme"), "acme", parent=None)
        )


def test_missing_templates_directory_is_refused(registry, tmp_path):
    root_without_templates = tmp_path / "empty"
    root_without_templates.mkdir()

    with pytest.raises(ThemeRegistrationError, match="templates"):
        registry.register(_descriptor(root_without_templates, "acme"))


@pytest.mark.parametrize(
    "tokens",
    [
        {"color-primary": "#000"},
        {"--vbwd-Color": "#000"},
        {"--other-color": "#000"},
    ],
)
def test_bad_token_name_is_refused(registry, tmp_path, tokens):
    root = _theme_root(tmp_path, "acme")
    (root / "tokens.json").write_text(json.dumps(tokens))

    with pytest.raises(ThemeRegistrationError, match="token name"):
        registry.register(_descriptor(root, "acme"))


@pytest.mark.parametrize("injected_value", ["red;}", "<x>", "a{b", 7])
def test_token_value_injection_is_refused(registry, tmp_path, injected_value):
    root = _theme_root(tmp_path, "acme")
    (root / "tokens.json").write_text(
        json.dumps({"--vbwd-color-primary": injected_value})
    )

    with pytest.raises(ThemeRegistrationError, match="token value"):
        registry.register(_descriptor(root, "acme"))


def test_tokens_file_must_be_a_json_object(registry, tmp_path):
    root = _theme_root(tmp_path, "acme")
    (root / "tokens.json").write_text('["--vbwd-color-primary"]')

    with pytest.raises(ThemeRegistrationError, match="tokens.json"):
        registry.register(_descriptor(root, "acme"))


def test_valid_tokens_and_translations_are_accepted(registry, tmp_path):
    root = _theme_root(tmp_path, "acme")
    (root / "tokens.json").write_text(json.dumps({"--vbwd-color-primary": "#0a7f6f"}))
    (root / "translations").mkdir()
    (root / "translations" / "de.json").write_text(json.dumps({"Login": "Anmelden"}))

    registry.register(_descriptor(root, "acme"))

    assert registry.get("acme").root == root


@pytest.mark.parametrize(
    "file_content",
    ["{not json", '["Login"]', '{"Login": 1}', '{"Login": {"nested": "x"}}'],
)
def test_bad_translation_file_is_refused(registry, tmp_path, file_content):
    root = _theme_root(tmp_path, "acme")
    (root / "translations").mkdir()
    (root / "translations" / "de.json").write_text(file_content)

    with pytest.raises(ThemeRegistrationError, match="de.json"):
        registry.register(_descriptor(root, "acme"))


def test_registration_error_is_a_value_error():
    assert issubclass(ThemeRegistrationError, ValueError)


def test_contributed_template_paths_keep_insertion_order(registry, tmp_path):
    registry.add_contributed_template_path(tmp_path / "shop")
    registry.add_contributed_template_path(tmp_path / "cms")

    assert registry.contributed_template_paths() == [
        tmp_path / "shop",
        tmp_path / "cms",
    ]


def test_contributed_stylesheet_paths_keep_insertion_order(registry, tmp_path):
    (tmp_path / "shop").mkdir()
    (tmp_path / "cms").mkdir()
    registry.add_contributed_stylesheet_path(tmp_path / "shop")
    registry.add_contributed_stylesheet_path(tmp_path / "cms")

    assert registry.contributed_stylesheet_paths() == [
        tmp_path / "shop",
        tmp_path / "cms",
    ]


def test_a_contributed_stylesheet_path_must_be_a_directory(registry, tmp_path):
    with pytest.raises(ThemeRegistrationError, match="missing"):
        registry.add_contributed_stylesheet_path(tmp_path / "missing")
