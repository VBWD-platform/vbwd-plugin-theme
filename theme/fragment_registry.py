"""Theme fragment registry (S152-06b): the htmx islands adapters serve.

A fragment is a partial an htmx element fetches after the page loaded — a
quick-search dropdown, a form's result — at ``/_render/_fragment/<name>``
(W2: theme-internal, never a page path). Unlike a page it needs no
``X-VBWD-Render`` marker and answers GET (POST only when declared). Adapters
register fragments from ``on_enable``; the registry is sealed at mount time,
like the page registry.
"""
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Tuple

from .regions import REGIONS_PATH
from .theme_request import ThemeRequest

THEME_FRAGMENT_PREFIX = "/_render/_fragment/"
FRAGMENT_METHODS = ("GET", "POST")
READ_METHOD = "GET"
DEFAULT_FRAGMENT_METHODS = (READ_METHOD,)


class ThemeFragmentRedirect(Exception):
    """Raised by a fragment's ``build_context`` to end the htmx flow with a navigation.

    The fragment answers ``200`` with ``HX-Redirect: <location>`` and no body
    (htmx then sets ``window.location``) — e.g. a payment provider's hosted page
    or the checkout confirmation. ``location`` is chosen by the adapter.
    """

    def __init__(self, location: str) -> None:
        super().__init__(location)
        self.location = location


class ThemeFragmentRegistrationError(ValueError):
    """A fragment registration the theme refuses (prefix, methods, duplicate, late)."""


@dataclass(frozen=True)
class ThemeFragment:
    """One htmx island: a rule under the fragment prefix, a partial and its context.

    ``build_context(theme_request)`` receives the query arguments, plus the form
    fields on a POST, in ``theme_request.query_args``.
    """

    rule: str
    endpoint: str
    owner_fe_user_plugin: str
    template: str
    build_context: Callable[[ThemeRequest], Dict[str, Any]]
    methods: Tuple[str, ...] = DEFAULT_FRAGMENT_METHODS


class ThemeFragmentRegistry:
    """The fragments registered by adapters, sealed once the blueprint is built."""

    def __init__(self) -> None:
        self._fragments_by_rule: Dict[str, ThemeFragment] = {}
        self._sealed = False

    def register(self, fragment: ThemeFragment) -> None:
        if self._sealed:
            raise ThemeFragmentRegistrationError(
                f"theme fragment '{fragment.rule}' registered after the theme "
                "blueprint was mounted — register fragments in on_enable"
            )
        self._refuse_invalid(fragment)
        if fragment.rule in self._fragments_by_rule:
            raise ThemeFragmentRegistrationError(
                f"theme fragment '{fragment.rule}' is already registered"
            )
        if any(known.endpoint == fragment.endpoint for known in self.fragments()):
            raise ThemeFragmentRegistrationError(
                f"theme fragment endpoint '{fragment.endpoint}' is already registered"
            )
        self._fragments_by_rule[fragment.rule] = fragment

    def fragments(self) -> List[ThemeFragment]:
        return list(self._fragments_by_rule.values())

    def seal(self) -> None:
        self._sealed = True

    @staticmethod
    def _refuse_invalid(fragment: ThemeFragment) -> None:
        is_under_prefix = fragment.rule.startswith(THEME_FRAGMENT_PREFIX) and len(
            fragment.rule
        ) > len(THEME_FRAGMENT_PREFIX)
        if not is_under_prefix or fragment.rule == REGIONS_PATH:
            raise ThemeFragmentRegistrationError(
                f"theme fragment '{fragment.rule}' must live under "
                f"'{THEME_FRAGMENT_PREFIX}' and is not the regions fragment"
            )
        if not fragment.methods or not set(fragment.methods) <= set(FRAGMENT_METHODS):
            raise ThemeFragmentRegistrationError(
                f"theme fragment '{fragment.rule}': methods must be a non-empty "
                f"subset of {FRAGMENT_METHODS}"
            )
