"""Personalised-region tags (S152 D12): ``access``, ``permission`` and ``region``.

* ``{% access "pro", "gold" %}…{% else %}…{% endaccess %}`` — true branch iff the
  viewer holds ANY of the access-level slugs;
* ``{% permission "booking.manage" %}…{% else %}…{% endpermission %}`` — wildcard
  semantics of fe-user ``hasUserPermission``;
* ``{% region %}…{% endregion %}`` — anything identity-dependent (a greeting).

Each renders inside ``<div data-vbwd-region="rN">``. Ids are sequential per
render in document order, so the anonymous render and the viewer re-render of
the same page number their regions identically. A tag nested inside another
region renders without a marker and takes no id — the outer region is swapped
as a whole — so a region inside a gated branch never shifts later ids.
In an anonymous render the gated branch is never executed: its markup is not in
the bytes at all.
"""
from typing import Callable, Dict, Iterable, List, Optional

from jinja2 import nodes
from jinja2.exceptions import TemplateRuntimeError
from jinja2.ext import Extension
from jinja2.parser import Parser
from jinja2.runtime import Context
from markupsafe import Markup

from .viewer import Viewer, viewer_has_any_access_level, viewer_has_permission

REGION_STATE_CONTEXT_KEY = "vbwd_region_state"
REGION_ID_PREFIX = "r"
REGION_MARKUP = '<div data-vbwd-region="{}">{}</div>'


class RegionRenderState:
    """One render's region numbering and the inner HTML of each top-level region."""

    def __init__(self, viewer: Viewer) -> None:
        self.viewer = viewer
        self.contents_by_id: Dict[str, str] = {}
        self._issued_count = 0
        self._open_depth = 0

    def open_region(self) -> Optional[str]:
        """The next id for a top-level region; ``None`` inside another region."""
        self._open_depth += 1
        if self._open_depth > 1:
            return None
        self._issued_count += 1
        return f"{REGION_ID_PREFIX}{self._issued_count}"

    def close_region(self, region_id: Optional[str], inner_html: str) -> None:
        self._open_depth -= 1
        if region_id is not None:
            self.contents_by_id[region_id] = inner_html


def _region_state(context: Context) -> RegionRenderState:
    region_state = context.get(REGION_STATE_CONTEXT_KEY)
    if not isinstance(region_state, RegionRenderState):
        raise TemplateRuntimeError(
            "region tags need the theme page render context "
            "(import macros 'with context')"
        )
    return region_state


class RegionTagsExtension(Extension):
    """Registers the three region tags on a theme's ``SandboxedEnvironment``."""

    tags = {"access", "permission", "region"}

    def parse(self, parser: Parser) -> nodes.Node:
        tag_token = next(parser.stream)
        tag_name = tag_token.value
        end_token = f"name:end{tag_name}"
        if tag_name == "region":
            body = parser.parse_statements((end_token,), drop_needle=True)
            return self._region_node(body, tag_token.lineno)
        names = self._parse_names(parser)
        true_body = parser.parse_statements(("name:else", end_token))
        else_body: List[nodes.Node] = []
        if next(parser.stream).test("name:else"):
            else_body = parser.parse_statements((end_token,), drop_needle=True)
        check_method = (
            "_viewer_has_any_access_level"
            if tag_name == "access"
            else "_viewer_has_permission"
        )
        test = self.call_method(check_method, [nodes.ContextReference(), names])
        branch = nodes.If(test, true_body, [], else_body, lineno=tag_token.lineno)
        return self._region_node([branch], tag_token.lineno)

    @staticmethod
    def _parse_names(parser: Parser) -> nodes.List:
        names = [parser.parse_expression()]
        while parser.stream.skip_if("comma"):
            names.append(parser.parse_expression())
        return nodes.List(names)

    def _region_node(self, body: List[nodes.Node], lineno: int) -> nodes.CallBlock:
        wrap_call = self.call_method("_wrap_region", [nodes.ContextReference()])
        return nodes.CallBlock(wrap_call, [], [], body, lineno=lineno)

    @staticmethod
    def _viewer_has_any_access_level(context: Context, slugs: Iterable[str]) -> bool:
        return viewer_has_any_access_level(_region_state(context).viewer, slugs)

    @staticmethod
    def _viewer_has_permission(context: Context, permissions: List[str]) -> bool:
        viewer = _region_state(context).viewer
        return any(viewer_has_permission(viewer, name) for name in permissions)

    @staticmethod
    def _wrap_region(context: Context, caller: Callable[[], str]) -> Markup:
        region_state = _region_state(context)
        region_id = region_state.open_region()
        inner_html = Markup(caller())
        region_state.close_region(region_id, str(inner_html))
        if region_id is None:
            return inner_html
        return Markup(REGION_MARKUP).format(region_id, inner_html)
