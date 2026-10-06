"""S152-02 / D8 — template resolution: operator → child → parent → basic → contributed."""
import os
from pathlib import Path
from typing import Optional

import pytest
from jinja2 import Environment, TemplateNotFound

from plugins.theme.theme.template_loader import ThemeTemplateLoader
from plugins.theme.theme.theme_registry import (
    BASIC_THEME_SLUG,
    ThemeDescriptor,
    ThemeRegistry,
)

TEMPLATE_NAME = "page.html.j2"


def _write_template(templates_directory: Path, name: str, content: str) -> None:
    template_path = templates_directory / name
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(content)


def _register(
    registry: ThemeRegistry, base: Path, slug: str, parent: Optional[str]
) -> Path:
    root = base / "themes" / slug
    (root / "templates").mkdir(parents=True)
    registry.register(ThemeDescriptor(slug=slug, name=slug, parent=parent, root=root))
    return root / "templates"


@pytest.fixture
def layout(tmp_path):
    """basic ← acme ← acme_dark, an operator dir for acme_dark, one contributed dir."""
    registry = ThemeRegistry()
    directories = {
        "basic": _register(registry, tmp_path, BASIC_THEME_SLUG, None),
        "acme": _register(registry, tmp_path, "acme", BASIC_THEME_SLUG),
        "acme_dark": _register(registry, tmp_path, "acme_dark", "acme"),
        "operator": tmp_path / "var" / "assets" / "theme" / "acme_dark" / "templates",
        "contributed": tmp_path / "adapter" / "templates",
    }
    directories["operator"].mkdir(parents=True)
    directories["contributed"].mkdir(parents=True)
    registry.add_contributed_template_path(directories["contributed"])
    return registry, directories


def _render(
    registry: ThemeRegistry, operator_directory: Path, name: str = TEMPLATE_NAME
) -> str:
    loader = ThemeTemplateLoader(registry, "acme_dark", operator_directory)
    return Environment(loader=loader).get_template(name).render()


@pytest.mark.parametrize(
    "winning_level, levels_with_the_template",
    [
        ("operator", ["operator", "acme_dark", "acme", "basic", "contributed"]),
        ("acme_dark", ["acme_dark", "acme", "basic", "contributed"]),
        ("acme", ["acme", "basic", "contributed"]),
        ("basic", ["basic", "contributed"]),
        ("contributed", ["contributed"]),
    ],
)
def test_first_hit_wins_in_precedence_order(
    layout, winning_level, levels_with_the_template
):
    registry, directories = layout
    for level in levels_with_the_template:
        _write_template(directories[level], TEMPLATE_NAME, f"from {level}")

    assert _render(registry, directories["operator"]) == f"from {winning_level}"


def test_a_theme_overrides_a_contributed_partial(layout):
    registry, directories = layout
    _write_template(directories["contributed"], "shop/_card.html.j2", "adapter card")
    _write_template(directories["basic"], "shop/_card.html.j2", "basic card")

    assert (
        _render(registry, directories["operator"], "shop/_card.html.j2") == "basic card"
    )


def test_namespaced_name_resolves_only_in_that_theme(layout):
    registry, directories = layout
    _write_template(directories["operator"], TEMPLATE_NAME, "operator")
    _write_template(directories["acme_dark"], TEMPLATE_NAME, "child")
    _write_template(directories["basic"], TEMPLATE_NAME, "basic")

    assert (
        _render(registry, directories["operator"], f"@basic/{TEMPLATE_NAME}") == "basic"
    )


def test_namespaced_name_never_falls_back(layout):
    registry, directories = layout
    _write_template(directories["contributed"], TEMPLATE_NAME, "contributed")
    _write_template(directories["acme_dark"], TEMPLATE_NAME, "child")

    with pytest.raises(TemplateNotFound):
        _render(registry, directories["operator"], f"@basic/{TEMPLATE_NAME}")


def test_namespaced_name_of_an_unknown_theme_is_not_found(layout):
    registry, directories = layout

    with pytest.raises(TemplateNotFound):
        _render(registry, directories["operator"], f"@nope/{TEMPLATE_NAME}")


def test_child_extends_same_named_parent_with_super(layout):
    registry, directories = layout
    _write_template(
        directories["basic"],
        TEMPLATE_NAME,
        "<main>{% block body %}basic body{% endblock %}</main>",
    )
    _write_template(
        directories["acme_dark"],
        TEMPLATE_NAME,
        '{% extends "@basic/page.html.j2" %}'
        "{% block body %}child body + {{ super() }}{% endblock %}",
    )

    assert (
        _render(registry, directories["operator"])
        == "<main>child body + basic body</main>"
    )


def test_missing_template_is_not_found(layout):
    registry, directories = layout

    with pytest.raises(TemplateNotFound):
        _render(registry, directories["operator"], "missing.html.j2")


def test_path_traversal_is_not_found(layout):
    registry, directories = layout
    _write_template(directories["basic"].parent, "secret.html.j2", "secret")

    with pytest.raises(TemplateNotFound):
        _render(registry, directories["operator"], "../secret.html.j2")


def test_uptodate_turns_false_when_the_file_changes(layout):
    registry, directories = layout
    _write_template(directories["basic"], TEMPLATE_NAME, "v1")
    loader = ThemeTemplateLoader(registry, "acme_dark", directories["operator"])
    _source, filename, uptodate = loader.get_source(Environment(), TEMPLATE_NAME)
    assert uptodate()

    template_path = Path(filename)
    original_modification_time = template_path.stat().st_mtime
    template_path.write_text("v2")
    os.utime(
        template_path, (original_modification_time + 5, original_modification_time + 5)
    )

    assert not uptodate()
