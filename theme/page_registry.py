"""Theme page registry (S152 D7 + W2): the seam theme adapters register into.

An adapter registers each page it renders, at its PUBLIC path, from its
``on_enable``. The core enables every plugin before it mounts any blueprint
(``vbwd/app.py``: ``load_persisted_state()`` runs before the
``get_blueprint()`` loop), so the theme builds its blueprint from the registry
once, at mount time, and seals the registry: a later registration raises
instead of silently never being routed.

S154 D9: plugins owning public fe-user SPA routes (under a configurable base)
declare them structurally through :class:`FeUserRouteOwner`; catch-all adapters
read them per request with :func:`resolve_fe_user_route_prefixes`.
"""
import logging
from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Protocol,
    Sequence,
    runtime_checkable,
)

from flask import current_app

from .theme_request import ThemeRequest

THEME_PLUGIN_NAME = "theme"

# The blueprint every page endpoint lives on (``theme.<page endpoint>``).
THEME_BLUEPRINT_NAME = "theme"

# D7 — paths the SPA always owns; nginx never proxies them and the theme
# refuses them. One constant, so a new SPA-only plugin is a one-line change.
SPA_ONLY_PREFIXES = ("/dashboard", "/tuktuk")

# W2 — theme-internal fragments and assets; never a page path.
THEME_INTERNAL_PREFIX = "/_render"

logger = logging.getLogger(__name__)

PUBLIC_PAGE = "public"
USER_PAGE = "user"
PAGE_AUTH_LEVELS = (PUBLIC_PAGE, USER_PAGE)


class ThemePageRegistrationError(ValueError):
    """A page registration the theme refuses (reserved path, duplicate, late)."""


@dataclass(frozen=True)
class ThemePage:
    """One themed page: a Flask rule at its public path, a template and its context.

    The theme renders ``template`` with ``build_context(theme_request)``; an
    adapter never builds a response itself. ``owner_fe_user_plugin`` is the
    fe-user plugin whose enabled flag governs the page (same toggle as the SPA).
    """

    rule: str
    endpoint: str
    owner_fe_user_plugin: str
    priority: int
    auth: str
    template: str
    build_context: Callable[[ThemeRequest], Dict[str, Any]]


def _is_under_prefix(path: str, prefix: str) -> bool:
    """Segment-wise prefix match: ``/dashboard/x`` yes, ``/dashboards`` no."""
    return path == prefix or path.startswith(prefix + "/")


def is_under_any_prefix(path: str, prefixes: Iterable[str]) -> bool:
    """Segment-wise match of ``path`` against any of ``prefixes``."""
    return any(_is_under_prefix(path, prefix) for prefix in prefixes)


@runtime_checkable
class FeUserRouteOwner(Protocol):
    """S154 D9 — a plugin whose fe-user companion mounts public SPA routes that no
    theme adapter renders, possibly under an operator-configurable base.

    Structural on purpose: domain plugins never import the theme (S152 R1), so a
    plugin opts in by defining this one method and the theme discovers it among
    the ENABLED plugins (the ``PayoutProvider`` discovery pattern, by shape). It
    is read per request, so a config change needs no re-registration.
    """

    def fe_user_route_prefixes(self) -> Sequence[str]:
        """Absolute, segment-wise path prefixes the fe-user SPA owns (``/base``)."""
        ...


def _is_valid_route_prefix(prefix: str) -> bool:
    """Absolute and not the root: ``/`` would hand every path to the SPA."""
    return prefix.startswith("/") and bool(prefix.strip("/"))


def collect_fe_user_route_prefixes(plugins: Iterable[object]) -> List[str]:
    """The valid prefixes declared by every :class:`FeUserRouteOwner` in ``plugins``."""
    prefixes: List[str] = []
    for plugin in plugins:
        if not isinstance(plugin, FeUserRouteOwner):
            continue
        for prefix in plugin.fe_user_route_prefixes():
            if _is_valid_route_prefix(prefix):
                prefixes.append(prefix)
            else:
                logger.warning(
                    "[theme] ignoring fe-user route prefix %r of %s: not an "
                    "absolute, non-root path",
                    prefix,
                    type(plugin).__name__,
                )
    return prefixes


def resolve_fe_user_route_prefixes() -> List[str]:
    """The fe-user route prefixes of the running app's enabled plugins."""
    plugin_manager = getattr(current_app, "plugin_manager")
    return collect_fe_user_route_prefixes(plugin_manager.get_enabled_plugins())


class ThemePageRegistry:
    """The pages registered by adapters, sealed once the blueprint is built."""

    def __init__(self) -> None:
        self._pages_by_rule: Dict[str, ThemePage] = {}
        self._sealed = False

    def register(self, page: ThemePage) -> None:
        if self._sealed:
            raise ThemePageRegistrationError(
                f"theme page '{page.rule}' ({page.owner_fe_user_plugin}) registered after "
                "the theme blueprint was mounted — register pages in on_enable"
            )
        self._refuse_reserved_path(page.rule)
        if page.auth not in PAGE_AUTH_LEVELS:
            raise ThemePageRegistrationError(
                f"theme page '{page.rule}': auth must be one of {PAGE_AUTH_LEVELS}"
            )
        if page.rule in self._pages_by_rule:
            raise ThemePageRegistrationError(
                f"theme page '{page.rule}' is already registered by "
                f"'{self._pages_by_rule[page.rule].owner_fe_user_plugin}'"
            )
        if any(known.endpoint == page.endpoint for known in self.pages()):
            raise ThemePageRegistrationError(
                f"theme page endpoint '{page.endpoint}' is already registered"
            )
        self._pages_by_rule[page.rule] = page

    def pages(self) -> List[ThemePage]:
        """Registered pages, highest priority first."""
        return sorted(
            self._pages_by_rule.values(), key=lambda page: page.priority, reverse=True
        )

    def seal(self) -> None:
        self._sealed = True

    @staticmethod
    def _refuse_reserved_path(rule: str) -> None:
        for prefix in SPA_ONLY_PREFIXES + (THEME_INTERNAL_PREFIX,):
            if _is_under_prefix(rule, prefix):
                raise ThemePageRegistrationError(
                    f"theme page '{rule}' is under the reserved prefix '{prefix}'"
                )


def resolve_theme_plugin():
    """The running app's theme plugin; adapters and child themes reach it through here."""
    plugin_manager = getattr(current_app, "plugin_manager")
    theme_plugin = plugin_manager.get_plugin(THEME_PLUGIN_NAME)
    if theme_plugin is None:
        raise LookupError("theme plugin is not installed")
    return theme_plugin


def resolve_theme_page_registry() -> ThemePageRegistry:
    """The registry of the running app's theme plugin (adapters call this)."""
    return resolve_theme_plugin().page_registry
