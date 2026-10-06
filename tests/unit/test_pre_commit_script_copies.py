"""Every theme repo ships the same ``bin/pre-commit-check.sh`` as this canonical copy.

The script derives the plugin name from its repo directory, so one file serves all seven
repos. Siblings are looked up next to this repo, both as SDK dirs (``theme_cms``) and as
standalone clones (``vbwd-plugin-theme-cms``); a sibling that is not checked out skips.
"""
import os
from pathlib import Path
from typing import Optional

import pytest

THEME_REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_SCRIPT = THEME_REPO_ROOT / "bin" / "pre-commit-check.sh"
SIBLING_PLUGIN_NAMES = (
    "theme_cms",
    "theme_checkout",
    "theme_shop",
    "theme_dataset",
    "theme_subscription",
    "theme_booking",
)


def _sibling_repo(plugin_name: str) -> Optional[Path]:
    standalone_name = "vbwd-plugin-" + plugin_name.replace("_", "-")
    for directory_name in (plugin_name, standalone_name):
        candidate = THEME_REPO_ROOT.parent / directory_name
        if candidate.is_dir():
            return candidate
    return None


def test_the_canonical_script_exists_and_is_executable():
    assert CANONICAL_SCRIPT.is_file()
    assert os.access(CANONICAL_SCRIPT, os.X_OK)


@pytest.mark.parametrize("plugin_name", SIBLING_PLUGIN_NAMES)
def test_each_sibling_repo_ships_a_byte_identical_copy(plugin_name):
    sibling_repo = _sibling_repo(plugin_name)
    if sibling_repo is None:
        pytest.skip(f"{plugin_name} is not checked out next to theme")
    sibling_script = sibling_repo / "bin" / "pre-commit-check.sh"
    assert sibling_script.is_file(), f"{plugin_name} has no bin/pre-commit-check.sh"
    assert (
        sibling_script.read_bytes() == CANONICAL_SCRIPT.read_bytes()
    ), f"{plugin_name}/bin/pre-commit-check.sh drifted from theme's canonical copy"
    assert os.access(sibling_script, os.X_OK), f"{plugin_name} copy is not executable"
