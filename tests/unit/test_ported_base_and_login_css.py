"""The basic theme's document base and `/login` CSS — the SPA's, ported.

The walkthroughs showed `/login` and every themed page without a CMS style
(`/checkout`, `/pay/*`) in browser defaults: the basic theme shipped no base rules
and no Login.vue styles. Ported here under the adapters' rules (S152-06c / 06d):

* ``_shared/base.css`` — App.vue's global ``*`` / ``body`` rules plus its
  public-page remap (``#app.app--public-light``: every themed page is public);
* ``public/login.css`` — Login.vue's scoped rules, scoped to ``.login-page``;
  every class the login templates use that Login.vue styles has a rule, and
  no invented rule;
* a literal colour only as the fallback of a ``var(--vbwd-…, <literal>)`` token,
  the fallbacks equal to the SPA literals, every ``--vbwd-base-*`` /
  ``--vbwd-login-*`` token documented in the theme guide.

The SPA-comparing half skips without the fe-user checkout next to vbwd-backend.
"""
from pathlib import Path

import pytest

from plugins.theme.tests.colour_tokens import (
    adapter_token_fallbacks,
    css_declarations,
    documented_colour_tokens,
    rendered_value,
    token_fallback_mismatches,
    unported_spa_colours,
)
from plugins.theme.tests.css_inventory import (
    hard_coded_colours,
    is_used,
    rule_classes,
    template_class_usage,
    vue_style_text,
)
from plugins.theme.theme.theme_registry import (
    BASIC_THEME_DESCRIPTOR,
    TOKEN_NAME_PATTERN,
)

BASIC_STATIC_DIRECTORY = BASIC_THEME_DESCRIPTOR.static_directory
BASE_CSS = BASIC_STATIC_DIRECTORY / "_shared" / "base.css"
LOGIN_CSS = BASIC_STATIC_DIRECTORY / "public" / "login.css"
LOGIN_TEMPLATES_DIRECTORY = (
    BASIC_THEME_DESCRIPTOR.root / "templates" / "_shared" / "auth"
)

BACKEND_ROOT = Path(__file__).resolve().parents[4]
FE_USER_SOURCE = BACKEND_ROOT.parent / "vbwd-fe-user" / "vue" / "src"
APP_VUE = FE_USER_SOURCE / "App.vue"
LOGIN_VUE = FE_USER_SOURCE / "views" / "Login.vue"
APP_BASE_SELECTORS = ("*", "body")
PUBLIC_PAGE_SELECTOR = "#app.app--public-light"
THEMED_PUBLIC_PAGE_SELECTOR = "body"

needs_spa_checkout = pytest.mark.skipif(
    not FE_USER_SOURCE.is_dir(),
    reason="the fe-user checkout is not next to vbwd-backend",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _used_styled_login_classes():
    static_classes, prefixes = template_class_usage(
        LOGIN_TEMPLATES_DIRECTORY.glob("*.j2")
    )
    styled = rule_classes(vue_style_text(_text(LOGIN_VUE)))
    return {name for name in styled if is_used(name, static_classes, prefixes)}


def _rendered(css_text: str, selector: str):
    return {
        (property_name, rendered_value(value))
        for ported_selector, property_name, value in css_declarations(css_text)
        if ported_selector == selector
    }


def test_the_basic_theme_ships_a_document_base_and_the_login_styles():
    assert "font-family" in _text(BASE_CSS)
    assert {"login-page", "login-card", "form-group", "error"} <= rule_classes(
        _text(LOGIN_CSS)
    )


def test_the_ported_css_carries_no_hard_coded_colour():
    assert hard_coded_colours(_text(BASE_CSS) + _text(LOGIN_CSS)) == []


@needs_spa_checkout
def test_every_used_login_class_has_a_ported_rule_and_none_is_invented():
    assert rule_classes(_text(LOGIN_CSS)) == _used_styled_login_classes()


@needs_spa_checkout
def test_every_login_colour_is_ported_with_the_spa_literal():
    login_css = _text(LOGIN_CSS)

    assert (
        unported_spa_colours([LOGIN_VUE], login_css, _used_styled_login_classes()) == []
    )
    assert token_fallback_mismatches([LOGIN_VUE], login_css, "login") == []


@needs_spa_checkout
def test_the_base_renders_the_app_global_rules_and_the_public_page_remap():
    app_style = vue_style_text(_text(APP_VUE))
    base_css = _text(BASE_CSS)

    for selector in APP_BASE_SELECTORS:
        assert _rendered(app_style, selector) <= _rendered(base_css, selector), selector
    assert _rendered(app_style, PUBLIC_PAGE_SELECTOR) <= _rendered(
        base_css, THEMED_PUBLIC_PAGE_SELECTOR
    )


@pytest.mark.parametrize("token_prefix", ["base", "login"])
def test_every_token_is_documented_with_its_default_and_vice_versa(token_prefix):
    css_text = _text(BASE_CSS) + _text(LOGIN_CSS)
    used = {
        token: sorted(fallbacks)
        for token, fallbacks in adapter_token_fallbacks(css_text, token_prefix).items()
    }
    documented = {
        token: [default]
        for token, default in documented_colour_tokens(token_prefix).items()
    }

    assert used and used == documented
    assert [name for name in used if not TOKEN_NAME_PATTERN.match(name)] == []
