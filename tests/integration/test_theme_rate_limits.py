"""S152-04 — ``test_render_blueprint_is_limiter_exempt_but_inner_api_limits_apply``.

The app runs with the limiter ON and a tight application-wide limit. Page hits
on the ``/_render``-mounted theme blueprint are exempt (navigations are not API
calls), while every inner C2 call keeps its limits: a page whose context calls
a rate-limited ``/api/v1`` route sees the 429 as a ``ThemeApiError``.
"""
import pytest

from plugins.theme.tests.integration.fake_adapter import (
    FAKE_LIMITED_PAGE_PATH,
    FAKE_PAGE_PATH,
    build_fake_api_blueprint,
    received_api_error_statuses,
)

RENDER_HEADER = {"X-VBWD-Render": "1"}
APPLICATION_RATE_LIMIT = "1 per minute"
PAGE_HITS_OVER_THE_LIMIT = 4
TOO_MANY_REQUESTS = 429


class EnglishOnlyLanguagePolicy:
    """A ThemeLanguagePolicy that asks no inner API, so only the pages' own calls count."""

    def enabled_languages(self, theme_request):
        return ("en",)

    def default_language(self, theme_request):
        return "en"


@pytest.fixture
def rate_limited_client(make_client):
    from vbwd.extensions import limiter

    client, app = make_client(
        "theme",
        extra_config={
            "RATELIMIT_ENABLED": True,
            "RATELIMIT_STORAGE_URL": "memory://",
            "RATELIMIT_APPLICATION": APPLICATION_RATE_LIMIT,
        },
        api_blueprints=[build_fake_api_blueprint()],
    )
    # The default policy's languages lookup is an inner call too and would spend
    # the 1-per-minute budget this test reserves for the limited page.
    app.plugin_manager.get_plugin("theme").set_language_policy(
        EnglishOnlyLanguagePolicy()
    )
    limiter.reset()
    yield client
    # The limiter is process-global: drop the application limit so no later
    # test inherits it, and clear the counters.
    limiter.limit_manager.set_application_limits([])
    limiter.reset()


def test_render_blueprint_is_limiter_exempt_but_inner_api_limits_apply(
    rate_limited_client,
):
    page_statuses = [
        rate_limited_client.get(FAKE_PAGE_PATH, headers=RENDER_HEADER).status_code
        for _ in range(PAGE_HITS_OVER_THE_LIMIT)
    ]
    assert page_statuses == [200] * PAGE_HITS_OVER_THE_LIMIT

    first = rate_limited_client.get(FAKE_LIMITED_PAGE_PATH, headers=RENDER_HEADER)
    second = rate_limited_client.get(FAKE_LIMITED_PAGE_PATH, headers=RENDER_HEADER)

    assert first.status_code == 200
    assert "answer=42" in first.get_data(as_text=True)
    assert received_api_error_statuses == [TOO_MANY_REQUESTS]
    assert second.status_code == 500
    assert 'data-testid="error-500"' in second.get_data(as_text=True)
