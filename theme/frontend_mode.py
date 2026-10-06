"""Frontend mode switch (S152 D10): ``VBWD_FRONTEND_MODE`` = ``vue`` | ``theme``.

The mode lives only in the environment (``vbwd-backend/.env`` via compose).
``vue`` (the default) means the Vue SPA serves every page and the theme mounts
no page route; ``theme`` means the theme renders the pages its adapters own.
"""
import os
from enum import Enum

from vbwd.plugins.errors import PluginConfigurationError

FRONTEND_MODE_ENVIRONMENT_VARIABLE = "VBWD_FRONTEND_MODE"


class FrontendMode(str, Enum):
    VUE = "vue"
    THEME = "theme"


DEFAULT_FRONTEND_MODE = FrontendMode.VUE


def read_frontend_mode() -> FrontendMode:
    """Return the configured mode; raise ``PluginConfigurationError`` if invalid."""
    raw_value = os.environ.get(FRONTEND_MODE_ENVIRONMENT_VARIABLE)
    if raw_value is None or not raw_value.strip():
        return DEFAULT_FRONTEND_MODE
    try:
        return FrontendMode(raw_value.strip().lower())
    except ValueError:
        raise PluginConfigurationError(
            f"theme: {FRONTEND_MODE_ENVIRONMENT_VARIABLE}='{raw_value}' is invalid "
            f"— use 'vue' or 'theme'"
        ) from None
