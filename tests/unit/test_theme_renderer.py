"""S152-02 — ThemeRenderer: sandbox, autoescape, undefined policy, fallback, overrides."""
import logging
import os
from pathlib import Path

import pytest
from flask import Blueprint, Flask
from jinja2 import UndefinedError
from jinja2.sandbox import SecurityError

from plugins.theme.theme.renderer import ThemeRenderer
from plugins.theme.theme.static_assets import ThemeStaticAssets
from plugins.theme.theme.stylesheet import content_hash
from plugins.theme.theme.theme_registry import (
    BASIC_THEME_SLUG,
    ThemeDescriptor,
    ThemeRegistry,
)

TEMPLATE_NAME = "probe.html.j2"


def _write(templates_directory: Path, name: str, content: str) -> Path:
    template_path = templates_directory / name
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(content)
    return template_path


@pytest.fixture
def basic_templates(tmp_path) -> Path:
    templates_directory = tmp_path / "themes" / "basic" / "templates"
    templates_directory.mkdir(parents=True)
    return templates_directory


@pytest.fixture
def registry(basic_templates) -> ThemeRegistry:
    theme_registry = ThemeRegistry()
    theme_registry.register(
        ThemeDescriptor(
            slug=BASIC_THEME_SLUG,
            name="Basic",
            parent=None,
            root=basic_templates.parent,
        )
    )
    return theme_registry


@pytest.fixture(autouse=True)
def isolated_var_directory(tmp_path, monkeypatch) -> Path:
    var_directory = tmp_path / "var"
    monkeypatch.setenv("VBWD_VAR_DIR", str(var_directory))
    return var_directory


def _app(testing: bool = True, debug: bool = False) -> Flask:
    app = Flask(__name__)
    app.testing = testing
    app.debug = debug
    return app


def _renderer(
    registry: ThemeRegistry, active_slug: str = BASIC_THEME_SLUG
) -> ThemeRenderer:
    return ThemeRenderer(registry, lambda: active_slug)


def _render(renderer: ThemeRenderer, app: Flask, context=None) -> str:
    with app.app_context():
        return renderer.render(TEMPLATE_NAME, context or {})


def test_output_is_autoescaped(registry, basic_templates):
    _write(basic_templates, TEMPLATE_NAME, '{{ "<script>" }}')

    assert _render(_renderer(registry), _app()) == "&lt;script&gt;"


def test_sandbox_blocks_dunder_access(registry, basic_templates):
    _write(basic_templates, TEMPLATE_NAME, "{{ ''.__class__.__mro__ }}")

    with pytest.raises(SecurityError):
        _render(_renderer(registry), _app())


def test_missing_variable_raises_when_testing(registry, basic_templates):
    _write(basic_templates, TEMPLATE_NAME, "{{ missing_variable }}")

    with pytest.raises(UndefinedError):
        _render(_renderer(registry), _app(testing=True))


def test_missing_variable_renders_empty_outside_testing(registry, basic_templates):
    _write(basic_templates, TEMPLATE_NAME, "[{{ missing_variable }}]")

    assert _render(_renderer(registry), _app(testing=False)) == "[]"


def test_context_reaches_the_template(registry, basic_templates):
    _write(basic_templates, TEMPLATE_NAME, "Hello {{ visitor }}")

    assert _render(_renderer(registry), _app(), {"visitor": "Ada"}) == "Hello Ada"


def test_unknown_active_theme_falls_back_to_basic_with_one_warning(
    registry, basic_templates, caplog
):
    _write(basic_templates, TEMPLATE_NAME, "basic")
    renderer = _renderer(registry, active_slug="ghost")

    with caplog.at_level(logging.WARNING):
        first = _render(renderer, _app())
        second = _render(renderer, _app())

    assert first == second == "basic"
    warnings = [record for record in caplog.records if "ghost" in record.getMessage()]
    assert len(warnings) == 1


def test_operator_override_directory_wins(
    registry, basic_templates, isolated_var_directory
):
    _write(basic_templates, TEMPLATE_NAME, "bundled")
    _write(
        isolated_var_directory / "assets" / "theme" / "basic" / "templates",
        TEMPLATE_NAME,
        "op",
    )

    assert _render(_renderer(registry), _app()) == "op"


def _bump_modification_time(template_path: Path) -> None:
    modification_time = template_path.stat().st_mtime + 5
    os.utime(template_path, (modification_time, modification_time))


def test_environment_is_cached_until_invalidated(registry, basic_templates):
    template_path = _write(basic_templates, TEMPLATE_NAME, "v1")
    renderer = _renderer(registry)
    app = _app(testing=True, debug=False)
    assert _render(renderer, app) == "v1"

    template_path.write_text("v2")
    _bump_modification_time(template_path)
    assert _render(renderer, app) == "v1"

    renderer.invalidate()
    assert _render(renderer, app) == "v2"


def test_templates_auto_reload_in_debug(registry, basic_templates):
    template_path = _write(basic_templates, TEMPLATE_NAME, "v1")
    renderer = _renderer(registry)
    app = _app(testing=True, debug=True)
    assert _render(renderer, app) == "v1"

    template_path.write_text("v2")
    _bump_modification_time(template_path)

    assert _render(renderer, app) == "v2"


def test_globals_frontend_mode_gettext_and_asset(
    registry, basic_templates, monkeypatch
):
    monkeypatch.setenv("VBWD_FRONTEND_MODE", "theme")
    _write(
        basic_templates,
        TEMPLATE_NAME,
        "{{ frontend_mode }}|{{ _('Log in') }}|{{ asset('css/site.css') }}",
    )

    (basic_templates.parent / "static" / "css").mkdir(parents=True)
    (basic_templates.parent / "static" / "css" / "site.css").write_text(".site{}")

    assert _render(_renderer(registry), _app()) == (
        "theme|Log in|/_render/_theme/static/basic/css/site.css?v="
        + content_hash(b".site{}")
    )


def test_theme_stylesheet_url_global_carries_the_stylesheet_hash(
    registry, basic_templates
):
    _write(basic_templates, TEMPLATE_NAME, "{{ theme_stylesheet_url() }}")
    expected_url = ThemeStaticAssets(registry).stylesheet_url(BASIC_THEME_SLUG)

    assert _render(_renderer(registry), _app()) == expected_url
    assert expected_url.startswith("/_render/_theme/public/theme.css?v=")


def test_url_for_page_resolves_on_the_theme_blueprint(registry, basic_templates):
    _write(
        basic_templates, TEMPLATE_NAME, "{{ url_for_page('shop_product', slug='mug') }}"
    )
    app = _app()
    blueprint = Blueprint("theme", __name__)
    blueprint.add_url_rule("/shop/product/<slug>", "shop_product", lambda slug: slug)
    app.register_blueprint(blueprint)

    with app.test_request_context("/"):
        assert _renderer(registry).render(TEMPLATE_NAME, {}) == "/shop/product/mug"
