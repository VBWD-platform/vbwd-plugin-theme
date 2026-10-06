"""Every theme repo ships the same shared repo files as this canonical copy.

``bin/pre-commit-check.sh`` derives the plugin name from its repo directory and
``tests/unit/test_wheel_packaging.py`` reads it from ``pyproject.toml``, so one file of each
serves all seven repos. Siblings are looked up next to this repo, both as SDK dirs (``theme_cms``) and as
standalone clones (``vbwd-plugin-theme-cms``); a sibling that is not checked out skips.
"""
import os
from pathlib import Path
from typing import Optional

import pytest

THEME_REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_SCRIPT = THEME_REPO_ROOT / "bin" / "pre-commit-check.sh"
CANONICAL_PACKAGING_TEST = (
    THEME_REPO_ROOT / "tests" / "unit" / "test_wheel_packaging.py"
)
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


@pytest.mark.parametrize("plugin_name", SIBLING_PLUGIN_NAMES)
def test_each_sibling_repo_ships_a_byte_identical_packaging_test(plugin_name):
    sibling_repo = _sibling_repo(plugin_name)
    if sibling_repo is None:
        pytest.skip(f"{plugin_name} is not checked out next to theme")
    sibling_test = sibling_repo / CANONICAL_PACKAGING_TEST.relative_to(THEME_REPO_ROOT)
    assert sibling_test.is_file(), f"{plugin_name} has no {sibling_test.name}"
    assert (
        sibling_test.read_bytes() == CANONICAL_PACKAGING_TEST.read_bytes()
    ), f"{plugin_name}/{sibling_test.name} drifted from theme's canonical copy"
