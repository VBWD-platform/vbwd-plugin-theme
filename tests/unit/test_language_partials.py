"""S152-05 / D13 + W3 — the generic hreflang and language-switcher partials of ``basic``.

Both take ``language_alternates`` (the W3 ``translations`` list: entries with
``language`` and ``url``), the final ``language`` and the ``current_url``. The
document includes both, so an adapter only passes the data.

hreflang follows the CMS SEO head (``seo_meta_builder._hreflang_tags``): with a
``current_url`` and a ``language`` it always emits self (+ each translation) +
x-default — also for an empty list — and nothing without a ``current_url``. The
switcher renders nothing for an empty list (there is nothing to switch to).
"""
import re

import pytest
from flask import Flask

from plugins.theme import ThemePlugin

HREFLANG = "_shared/partials/hreflang.html.j2"
SWITCHER = "_shared/partials/language_switcher.html.j2"
DOCUMENT = "_shared/document.html.j2"
LINK_PATTERN = re.compile(r'<link rel="alternate" hreflang="([^"]+)" href="([^"]+)">')
CURRENT_URL = "https://example.com/en/about"
ALTERNATES = [
    {"language": "de", "slug": "ueber-uns", "url": "https://example.com/de/ueber-uns"},
    {"language": "fr", "slug": "a-propos", "url": "https://example.com/fr/a-propos"},
]


@pytest.fixture(autouse=True)
def isolated_var_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("VBWD_VAR_DIR", str(tmp_path / "var"))


@pytest.fixture
def plugin() -> ThemePlugin:
    theme_plugin = ThemePlugin()
    theme_plugin.on_enable()
    return theme_plugin


def _render(plugin: ThemePlugin, template_name: str, context: dict) -> str:
    app = Flask(__name__)
    app.testing = True
    with app.app_context():
        return plugin.renderer.render(template_name, context)


def _context(alternates=ALTERNATES) -> dict:
    return {
        "language": "en",
        "current_url": CURRENT_URL,
        "language_alternates": alternates,
    }


def test_hreflang_lists_self_then_each_alternate_then_x_default(plugin):
    html = _render(plugin, HREFLANG, _context())

    assert LINK_PATTERN.findall(html) == [
        ("en", CURRENT_URL),
        ("de", "https://example.com/de/ueber-uns"),
        ("fr", "https://example.com/fr/a-propos"),
        ("x-default", CURRENT_URL),
    ]


def test_hreflang_emits_self_and_x_default_for_an_empty_list(plugin):
    html = _render(plugin, HREFLANG, _context(alternates=[]))

    assert LINK_PATTERN.findall(html) == [
        ("en", CURRENT_URL),
        ("x-default", CURRENT_URL),
    ]


def test_hreflang_renders_nothing_without_a_current_url(plugin):
    context = {"language": "en", "language_alternates": ALTERNATES}

    assert _render(plugin, HREFLANG, context).strip() == ""


def test_hreflang_escapes_urls(plugin):
    alternates = [{"language": "de", "url": 'https://example.com/"><script>'}]

    html = _render(plugin, HREFLANG, _context(alternates))

    assert "<script>" not in html
    assert "&#34;&gt;&lt;script&gt;" in html


def test_switcher_links_each_alternate_with_its_testid_and_language(plugin):
    html = _render(plugin, SWITCHER, _context())

    assert 'data-testid="language-switcher"' in html
    for alternate in ALTERNATES:
        language = alternate["language"]
        assert (
            f'<a href="{alternate["url"]}" hreflang="{language}" lang="{language}" '
            f'data-testid="language-switch-{language}" '
            f'data-vbwd-language="{language}">'
        ) in html


def test_switcher_marks_the_current_language_without_a_link(plugin):
    html = _render(plugin, SWITCHER, _context())

    assert (
        '<span aria-current="true" lang="en" data-testid="language-switch-en">'
    ) in html
    assert 'data-vbwd-language="en"' not in html


def test_switcher_renders_nothing_for_an_empty_list(plugin):
    assert _render(plugin, SWITCHER, _context(alternates=[])).strip() == ""


def test_the_document_includes_both_when_alternates_are_given(plugin):
    html = _render(plugin, DOCUMENT, _context())

    head, _separator, body = html.partition("</head>")
    assert ("x-default", CURRENT_URL) in LINK_PATTERN.findall(head)
    assert 'data-testid="language-switch-de"' in body


def test_the_document_has_neither_without_a_current_url_or_alternates(plugin):
    html = _render(plugin, DOCUMENT, {})

    assert "hreflang" not in html
    assert "language-switcher" not in html
