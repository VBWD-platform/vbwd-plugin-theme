"""S152-02 — the theme plugin's own ``basic`` theme and its wiring into the plugin."""
import hashlib
from types import SimpleNamespace

import pytest
from flask import Flask

from plugins.theme import ThemePlugin
from plugins.theme.theme.theme_registry import (
    BASIC_THEME_DESCRIPTOR,
    BASIC_THEME_SLUG,
)

SHARED = "_shared"


@pytest.fixture(autouse=True)
def isolated_var_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("VBWD_VAR_DIR", str(tmp_path / "var"))


@pytest.fixture
def enabled_plugin() -> ThemePlugin:
    plugin = ThemePlugin()
    plugin.on_enable()
    return plugin


def _app(saved_theme_config=None) -> Flask:
    app = Flask(__name__)
    app.testing = True
    if saved_theme_config is not None:
        app.config_store = SimpleNamespace(
            get_config=lambda plugin_name: saved_theme_config
            if plugin_name == "theme"
            else {}
        )
    return app


def _render(plugin: ThemePlugin, template_name: str, context=None, app=None) -> str:
    with (app or _app()).app_context():
        return plugin.renderer.render(template_name, context or {})


def test_on_enable_registers_the_basic_theme(enabled_plugin):
    assert enabled_plugin.theme_registry.chain(BASIC_THEME_SLUG) == [BASIC_THEME_SLUG]


def test_on_enable_twice_keeps_one_basic_theme(enabled_plugin):
    enabled_plugin.on_enable()

    assert enabled_plugin.theme_registry.is_registered(BASIC_THEME_SLUG)


def test_document_carries_the_frontend_sentinel_and_default_language(enabled_plugin):
    html = _render(enabled_plugin, f"{SHARED}/document.html.j2")

    assert '<meta name="vbwd-frontend" content="theme">' in html
    assert '<html lang="en">' in html
    assert '<meta charset="utf-8">' in html
    assert 'name="viewport"' in html


def test_document_uses_the_given_language(enabled_plugin):
    html = _render(enabled_plugin, f"{SHARED}/document.html.j2", {"language": "de"})

    assert '<html lang="de">' in html


def test_document_includes_header_and_footer(enabled_plugin):
    html = _render(enabled_plugin, f"{SHARED}/document.html.j2")

    assert "<header" in html
    assert "<footer" in html


@pytest.mark.parametrize("status_code", ["404", "403", "500"])
def test_error_pages_render_inside_the_document(enabled_plugin, status_code):
    html = _render(enabled_plugin, f"{SHARED}/errors/{status_code}.html.j2")

    assert '<meta name="vbwd-frontend" content="theme">' in html
    assert status_code in html


def test_form_macros_pass_the_testid_through(enabled_plugin, tmp_path):
    override_directory = tmp_path / "var" / "assets" / "theme" / "basic" / "templates"
    override_directory.mkdir(parents=True)
    (override_directory / "form_probe.html.j2").write_text(
        '{% import "_shared/macros/forms.html.j2" as forms %}'
        '{{ forms.input("email", "Email", type="email", testid="login-email") }}'
        '{{ forms.select("country", "Country", [("de", "Germany")], testid="country") }}'
        '{{ forms.button("Log in", testid="login-submit") }}'
    )

    html = _render(enabled_plugin, "form_probe.html.j2")

    assert 'data-testid="login-email"' in html
    assert 'type="email"' in html
    assert 'data-testid="country"' in html
    assert '<option value="de">Germany</option>' in html
    assert 'data-testid="login-submit"' in html


def test_active_theme_comes_from_the_saved_plugin_config(enabled_plugin):
    app = _app(saved_theme_config={"active_theme": "ghost"})

    with app.app_context():
        assert enabled_plugin.read_active_theme_slug() == "ghost"
        assert enabled_plugin.renderer.active_theme_slug() == BASIC_THEME_SLUG


def test_active_theme_defaults_to_basic_without_saved_config(enabled_plugin):
    with _app(saved_theme_config={}).app_context():
        assert enabled_plugin.read_active_theme_slug() == BASIC_THEME_SLUG


BASIC_STATIC_DIRECTORY = BASIC_THEME_DESCRIPTOR.static_directory
RUNTIME_SCRIPTS = (
    "_shared/js/htmx.min.js",
    "_shared/js/sse.js",
    "_shared/js/vbwd-theme.js",
)
VENDORED_MANIFEST = BASIC_STATIC_DIRECTORY / "_shared" / "js" / "VENDORED.md"


def test_document_links_the_versioned_theme_stylesheet(enabled_plugin):
    html = _render(enabled_plugin, f"{SHARED}/document.html.j2")

    expected_url = enabled_plugin.renderer.static_assets.stylesheet_url(
        BASIC_THEME_SLUG
    )
    assert f'<link rel="stylesheet" href="{expected_url}">' in html


def test_document_loads_the_runtime_scripts_deferred_at_the_end_of_body(
    enabled_plugin,
):
    html = _render(enabled_plugin, f"{SHARED}/document.html.j2")

    script_positions = []
    for script_path in RUNTIME_SCRIPTS:
        script_url = enabled_plugin.renderer.static_assets.asset_url(
            BASIC_THEME_SLUG, script_path
        )
        assert "?v=" in script_url, f"{script_path} is not shipped"
        script_tag = f'<script src="{script_url}" defer></script>'
        assert script_tag in html
        script_positions.append(html.index(script_tag))
    assert script_positions == sorted(script_positions)
    assert html.index("</main>") < script_positions[0]
    assert script_positions[-1] < html.index("</body>")


def test_document_body_attributes_block_lets_a_page_mark_auth_pending(
    enabled_plugin, tmp_path
):
    override_directory = tmp_path / "var" / "assets" / "theme" / "basic" / "templates"
    override_directory.mkdir(parents=True)
    (override_directory / "pending_probe.html.j2").write_text(
        '{% extends "_shared/document.html.j2" %}'
        '{% block body_attributes %} data-auth="pending"{% endblock %}'
    )

    assert '<body data-auth="pending">' in _render(
        enabled_plugin, "pending_probe.html.j2"
    )
    assert "<body>" in _render(enabled_plugin, f"{SHARED}/document.html.j2")


def test_basic_stylesheet_hides_private_chrome_while_auth_is_pending(enabled_plugin):
    css_text = enabled_plugin.renderer.static_assets.stylesheet(
        BASIC_THEME_SLUG
    ).css_text

    rule_start = css_text.index('[data-auth="pending"] .vbwd-private-chrome')
    rule_body = css_text[rule_start : css_text.index("}", rule_start)]
    assert "visibility: hidden" in rule_body


def _vendored_entries():
    """``| file | package | version | sha256 | license |`` rows of VENDORED.md."""
    entries = {}
    for line in VENDORED_MANIFEST.read_text(encoding="utf-8").splitlines():
        cells = [cell.strip(" `") for cell in line.strip().strip("|").split("|")]
        if len(cells) == 5 and cells[0].endswith(".js"):
            entries[cells[0]] = cells
    return entries


def test_vendored_manifest_checksums_match_the_shipped_files():
    entries = _vendored_entries()

    assert set(entries) == {"htmx.min.js", "sse.js"}
    for file_name, (_, package, version, sha256, license_name) in entries.items():
        shipped_file = VENDORED_MANIFEST.parent / file_name
        assert hashlib.sha256(shipped_file.read_bytes()).hexdigest() == sha256
        assert version and package and license_name
