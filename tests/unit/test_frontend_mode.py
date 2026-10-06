"""S152-01 / D10 — ``VBWD_FRONTEND_MODE`` parsing and fail-fast validation."""
import pytest

from vbwd.plugins.errors import PluginConfigurationError

from plugins.theme import ThemePlugin
from plugins.theme.theme.frontend_mode import FrontendMode, read_frontend_mode

MODE_VARIABLE = "VBWD_FRONTEND_MODE"


def test_mode_default_vue(monkeypatch):
    monkeypatch.delenv(MODE_VARIABLE, raising=False)

    assert read_frontend_mode() is FrontendMode.VUE


def test_blank_mode_is_the_default(monkeypatch):
    monkeypatch.setenv(MODE_VARIABLE, "   ")

    assert read_frontend_mode() is FrontendMode.VUE


@pytest.mark.parametrize("raw_value", ["theme", "THEME", " Theme \n"])
def test_mode_parses_theme_case_insensitively(monkeypatch, raw_value):
    monkeypatch.setenv(MODE_VARIABLE, raw_value)

    assert read_frontend_mode() is FrontendMode.THEME


def test_mode_parses_vue_explicitly(monkeypatch):
    monkeypatch.setenv(MODE_VARIABLE, "Vue")

    assert read_frontend_mode() is FrontendMode.VUE


def test_invalid_mode_raises_plugin_configuration_error(monkeypatch):
    monkeypatch.setenv(MODE_VARIABLE, "twig")

    with pytest.raises(PluginConfigurationError) as raised:
        ThemePlugin().validate_environment()

    assert str(raised.value) == (
        "theme: VBWD_FRONTEND_MODE='twig' is invalid — use 'vue' or 'theme'"
    )


def test_valid_mode_passes_validation(monkeypatch):
    monkeypatch.setenv(MODE_VARIABLE, "theme")

    assert ThemePlugin().validate_environment() is None
