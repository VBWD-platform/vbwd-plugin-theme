"""Manual render-budget benchmark for S152-04 (not a test; nothing asserts).

Renders a themed page whose context makes ``INNER_CALL_COUNT`` serial inner
API calls through core C2 (``call_api``), ``RENDER_COUNT`` times, inside the
real app, and prints p50 / p95 in milliseconds. Target: p95 < 300 ms.

Run inside the backend test container::

    docker compose run --rm -T test python plugins/theme/bin/render_budget.py
"""
import os
import statistics
import sys
import time
from types import MappingProxyType

BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))

RENDER_COUNT = 50
WARM_UP_RENDERS = 3
PERCENTILE_CUTS = 100
P50_INDEX = 49
P95_INDEX = 94
MILLISECONDS_PER_SECOND = 1000
BUDGET_MILLISECONDS = 300
# Public, DB-backed endpoints a themed page plausibly reads (all /api/v1, all C2).
INNER_API_PATHS = (
    "/api/v1/config",
    "/api/v1/config/languages",
    "/api/v1/settings/countries",
    "/api/v1/settings/payment-methods",
)
INNER_CALL_COUNT = len(INNER_API_PATHS)


BUDGET_PAGE_PATH = "/render-budget"


def _budget_page():
    from plugins.theme.theme.page_registry import ThemePage
    from plugins.theme.theme.theme_api import call_api

    def budget_context(theme_request) -> dict:
        responses = [call_api(theme_request, "GET", path) for path in INNER_API_PATHS]
        return {"page_title": f"budget ({len(responses)} inner calls)"}

    return ThemePage(
        rule=BUDGET_PAGE_PATH,
        endpoint="render_budget",
        owner_fe_user_plugin="render-budget",
        priority=0,
        auth="public",
        template="_shared/document.html.j2",
        build_context=budget_context,
    )


def _render_once(theme_plugin, budget_page) -> float:
    from flask import request

    from plugins.theme.theme.page_rendering import render_page
    from plugins.theme.theme.theme_request import ThemeRequest
    from plugins.theme.theme.viewer import ANONYMOUS_VIEWER

    started = time.perf_counter()
    theme_request = ThemeRequest(
        path=request.path,
        view_args=MappingProxyType({}),
        query_args=request.args,
        viewer=ANONYMOUS_VIEWER,
        http_request=request,
    )
    language_resolver = theme_plugin.language_resolver
    response = render_page(
        budget_page,
        language_resolver.with_pre_context_language(theme_request),
        theme_plugin.renderer,
        language_resolver,
    )
    if response.status_code != 200:
        raise SystemExit(f"budget page answered {response.status_code}")
    return (time.perf_counter() - started) * MILLISECONDS_PER_SECOND


def main() -> None:
    sys.path.insert(0, BACKEND_ROOT)
    from plugins.theme import ThemePlugin
    from vbwd.app import create_app
    from vbwd.config import get_database_url

    app = create_app(
        {"SQLALCHEMY_DATABASE_URI": get_database_url(), "RATELIMIT_ENABLED": False}
    )
    theme_plugin = ThemePlugin()
    theme_plugin.on_enable()
    budget_page = _budget_page()
    with app.test_request_context(BUDGET_PAGE_PATH):
        for _ in range(WARM_UP_RENDERS):
            _render_once(theme_plugin, budget_page)
        durations = [
            _render_once(theme_plugin, budget_page) for _ in range(RENDER_COUNT)
        ]
    cuts = statistics.quantiles(durations, n=PERCENTILE_CUTS)
    p50, p95 = cuts[P50_INDEX], cuts[P95_INDEX]
    verdict = "within" if p95 < BUDGET_MILLISECONDS else "OVER"
    print(
        f"{RENDER_COUNT} renders x {INNER_CALL_COUNT} inner C2 calls: "
        f"p50={p50:.1f} ms  p95={p95:.1f} ms  (budget p95<{BUDGET_MILLISECONDS} ms: {verdict})"
    )


if __name__ == "__main__":
    main()
