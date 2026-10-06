"""S152-04 / D12 — ``{% access %}``, ``{% permission %}`` and ``{% region %}`` tags.

Each tag renders inside ``<div data-vbwd-region="rN">``; ids are sequential per
render in document order and identical between the anonymous render and the
viewer re-render, so the runtime can swap regions by id.
"""
import re
from pathlib import Path

import pytest
from flask import Flask

from plugins.theme.theme.renderer import ThemeRenderer
from plugins.theme.theme.theme_registry import (
    BASIC_THEME_SLUG,
    ThemeDescriptor,
    ThemeRegistry,
)
from plugins.theme.theme.viewer import ANONYMOUS_VIEWER, Viewer

PAGE = "page.html.j2"
REGION_ID_PATTERN = re.compile(r'data-vbwd-region="([^"]+)"')


@pytest.fixture(autouse=True)
def isolated_var_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("VBWD_VAR_DIR", str(tmp_path / "var"))


@pytest.fixture
def templates_directory(tmp_path) -> Path:
    directory = tmp_path / "basic" / "templates"
    directory.mkdir(parents=True)
    return directory


@pytest.fixture
def renderer(templates_directory) -> ThemeRenderer:
    registry = ThemeRegistry()
    registry.register(
        ThemeDescriptor(
            slug=BASIC_THEME_SLUG,
            name="Basic",
            parent=None,
            root=templates_directory.parent,
        )
    )
    return ThemeRenderer(registry, lambda: BASIC_THEME_SLUG)


def _write(templates_directory: Path, name: str, content: str) -> None:
    (templates_directory / name).write_text(content, encoding="utf-8")


def _viewer(access_level_slugs=(), permissions=(), user_id="user-1") -> Viewer:
    return Viewer(
        user_id=user_id,
        access_level_slugs=frozenset(access_level_slugs),
        permissions=tuple(permissions),
    )


def _render(renderer, viewer=ANONYMOUS_VIEWER, context=None):
    app = Flask(__name__)
    app.testing = True
    with app.app_context():
        return renderer.render_with_regions(PAGE, context or {}, viewer=viewer)


ACCESS_PAGE = (
    '{% access "pro", "gold" %}GATED-PRO-PRICE{% else %}PUBLIC-PRICE{% endaccess %}'
)


def test_anonymous_access_outputs_only_the_else_branch_inside_a_region(
    renderer, templates_directory
):
    _write(templates_directory, PAGE, ACCESS_PAGE)

    rendered = _render(renderer)

    assert rendered.html == '<div data-vbwd-region="r1">PUBLIC-PRICE</div>'
    assert "GATED-PRO-PRICE" not in rendered.html


def test_access_opens_the_true_branch_for_any_listed_slug(
    renderer, templates_directory
):
    _write(templates_directory, PAGE, ACCESS_PAGE)

    rendered = _render(renderer, viewer=_viewer(access_level_slugs={"gold"}))

    assert rendered.html == '<div data-vbwd-region="r1">GATED-PRO-PRICE</div>'
    assert "PUBLIC-PRICE" not in rendered.html


def test_access_with_an_unknown_slug_renders_the_else_branch_without_error(
    renderer, templates_directory
):
    _write(
        templates_directory,
        PAGE,
        '{% access "no-such-level" %}GATED{% else %}PUBLIC{% endaccess %}',
    )

    rendered = _render(renderer, viewer=_viewer(access_level_slugs={"pro"}))

    assert rendered.html == '<div data-vbwd-region="r1">PUBLIC</div>'


def test_access_without_else_renders_an_empty_region_anonymously(
    renderer, templates_directory
):
    _write(templates_directory, PAGE, '{% access "pro" %}GATED{% endaccess %}')

    assert _render(renderer).html == '<div data-vbwd-region="r1"></div>'


PERMISSION_PAGE = (
    '{% permission "booking.manage" %}MANAGE-LINK{% else %}NO-LINK{% endpermission %}'
)


def test_permission_uses_wildcard_semantics(renderer, templates_directory):
    _write(templates_directory, PAGE, PERMISSION_PAGE)

    granted = _render(renderer, viewer=_viewer(permissions=("booking.*",)))
    super_admin = _render(renderer, viewer=_viewer(permissions=("*",)))
    refused = _render(renderer, viewer=_viewer(permissions=("booking.view",)))

    assert granted.html == '<div data-vbwd-region="r1">MANAGE-LINK</div>'
    assert super_admin.html == '<div data-vbwd-region="r1">MANAGE-LINK</div>'
    assert refused.html == '<div data-vbwd-region="r1">NO-LINK</div>'


def test_anonymous_permission_outputs_only_the_else_branch(
    renderer, templates_directory
):
    _write(templates_directory, PAGE, PERMISSION_PAGE)

    html = _render(renderer).html

    assert html == '<div data-vbwd-region="r1">NO-LINK</div>'
    assert "MANAGE-LINK" not in html


def test_region_renders_identity_dependent_content(renderer, templates_directory):
    _write(
        templates_directory,
        PAGE,
        "{% region %}{% if viewer.user_id %}Hello {{ viewer.user_id }}"
        "{% else %}Sign in{% endif %}{% endregion %}",
    )

    assert _render(renderer).html == '<div data-vbwd-region="r1">Sign in</div>'
    assert (
        _render(renderer, viewer=_viewer(user_id="ada")).html
        == '<div data-vbwd-region="r1">Hello ada</div>'
    )


def test_region_content_stays_autoescaped(renderer, templates_directory):
    _write(templates_directory, PAGE, "{% region %}{{ markup }}{% endregion %}")

    html = _render(renderer, context={"markup": "<script>x</script>"}).html

    assert html == ('<div data-vbwd-region="r1">&lt;script&gt;x&lt;/script&gt;</div>')


def test_ids_are_sequential_in_document_order_across_extends_and_include(
    renderer, templates_directory
):
    _write(
        templates_directory,
        "layout.html.j2",
        "{% region %}header{% endregion %}{% block content %}{% endblock %}"
        '{% include "footer.html.j2" %}',
    )
    _write(templates_directory, "footer.html.j2", "{% region %}footer{% endregion %}")
    _write(
        templates_directory,
        PAGE,
        '{% extends "layout.html.j2" %}{% block content %}'
        '{% access "pro" %}pro{% else %}public{% endaccess %}{% endblock %}',
    )

    anonymous_ids = REGION_ID_PATTERN.findall(_render(renderer).html)
    viewer_ids = REGION_ID_PATTERN.findall(
        _render(renderer, viewer=_viewer(access_level_slugs={"pro"})).html
    )

    assert anonymous_ids == ["r1", "r2", "r3"]
    assert viewer_ids == anonymous_ids


def test_a_region_nested_in_a_gated_branch_does_not_shift_later_ids(
    renderer, templates_directory
):
    _write(
        templates_directory,
        PAGE,
        '{% access "pro" %}{% region %}inner{% endregion %}{% endaccess %}'
        "{% region %}after{% endregion %}",
    )

    anonymous = _render(renderer)
    for_pro = _render(renderer, viewer=_viewer(access_level_slugs={"pro"}))

    assert REGION_ID_PATTERN.findall(anonymous.html) == ["r1", "r2"]
    assert REGION_ID_PATTERN.findall(for_pro.html) == ["r1", "r2"]
    assert for_pro.regions == {"r1": "inner", "r2": "after"}


def test_rendered_regions_map_each_id_to_its_inner_html(renderer, templates_directory):
    _write(
        templates_directory,
        PAGE,
        "<h1>Shop</h1>" + ACCESS_PAGE + "{% region %}greeting{% endregion %}",
    )

    rendered = _render(renderer, viewer=_viewer(access_level_slugs={"pro"}))

    assert rendered.regions == {"r1": "GATED-PRO-PRICE", "r2": "greeting"}


def test_each_render_starts_numbering_again(renderer, templates_directory):
    _write(templates_directory, PAGE, "{% region %}a{% endregion %}")

    _render(renderer)

    assert REGION_ID_PATTERN.findall(_render(renderer).html) == ["r1"]


def test_plain_render_returns_the_same_html(renderer, templates_directory):
    _write(templates_directory, PAGE, ACCESS_PAGE)
    app = Flask(__name__)
    app.testing = True

    with app.app_context():
        html = renderer.render(PAGE, {})

    assert html == '<div data-vbwd-region="r1">PUBLIC-PRICE</div>'
