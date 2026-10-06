"""S152-01 oracles (R1, D3) — the frontend mode never leaks into domain plugins.

1. No non-``theme*`` plugin imports ``plugins.theme*``, reads
   ``VBWD_FRONTEND_MODE``, or declares a ``theme*`` dependency.
2. No ``theme_*`` adapter imports a domain plugin: adapters talk to domain
   plugins over the public HTTP API only (core ``InternalApiClient``).

Same AST-walk approach as core's ``tests/unit/test_core_agnosticism.py``. The
filesystem is walked (not git), because gitignored plugin repos live on disk.
"""
import ast
import os
from pathlib import Path
from typing import Iterator, List, Tuple

import pytest

PLUGINS_DIRECTORY = Path(__file__).resolve().parents[3]
THEME_PREFIX = "theme"
FRONTEND_MODE_VARIABLE = "VBWD_FRONTEND_MODE"
SKIPPED_DIRECTORY_NAMES = {"__pycache__", ".git", "node_modules", ".venv", "venv"}


def _plugin_directories() -> List[Path]:
    return sorted(
        entry
        for entry in PLUGINS_DIRECTORY.iterdir()
        if entry.is_dir() and entry.name not in SKIPPED_DIRECTORY_NAMES
    )


def _python_files(plugin_directory: Path) -> Iterator[Path]:
    for directory_path, directory_names, file_names in os.walk(plugin_directory):
        directory_names[:] = [
            name for name in directory_names if name not in SKIPPED_DIRECTORY_NAMES
        ]
        for file_name in file_names:
            if file_name.endswith(".py"):
                yield Path(directory_path) / file_name


def _parse(file_path: Path) -> ast.AST:
    return ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))


def _imported_plugin_names(tree: ast.AST) -> Iterator[Tuple[int, str]]:
    """``(line, plugin)`` for every ``plugins.<plugin>…`` import in the tree."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module_names = [node.module or ""] if node.level == 0 else []
        elif isinstance(node, ast.Import):
            module_names = [alias.name for alias in node.names]
        else:
            continue
        for module_name in module_names:
            parts = module_name.split(".")
            if len(parts) >= 2 and parts[0] == "plugins":
                yield node.lineno, parts[1]


def _frontend_mode_literals(tree: ast.AST) -> Iterator[int]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value == FRONTEND_MODE_VARIABLE:
            yield node.lineno


def _declared_theme_dependencies(tree: ast.AST) -> Iterator[Tuple[int, str]]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function_name = getattr(node.func, "id", getattr(node.func, "attr", ""))
        if function_name != "PluginMetadata":
            continue
        for keyword in node.keywords:
            if keyword.arg != "dependencies":
                continue
            for element in getattr(keyword.value, "elts", []):
                if isinstance(element, ast.Constant) and str(element.value).startswith(
                    THEME_PREFIX
                ):
                    yield element.lineno, element.value


def _relative(file_path: Path) -> str:
    return str(file_path.relative_to(PLUGINS_DIRECTORY))


def test_domain_plugins_never_reference_the_theme():
    findings: List[str] = []
    domain_directories = [
        directory
        for directory in _plugin_directories()
        if not directory.name.startswith(THEME_PREFIX)
    ]
    assert domain_directories, "no domain plugin found — the walk is broken"
    for directory in domain_directories:
        for file_path in _python_files(directory):
            tree = _parse(file_path)
            for line, plugin_name in _imported_plugin_names(tree):
                if plugin_name.startswith(THEME_PREFIX):
                    findings.append(
                        f"{_relative(file_path)}:{line} imports plugins.{plugin_name}"
                    )
            for line in _frontend_mode_literals(tree):
                findings.append(
                    f"{_relative(file_path)}:{line} reads {FRONTEND_MODE_VARIABLE}"
                )
            for line, dependency in _declared_theme_dependencies(tree):
                findings.append(
                    f"{_relative(file_path)}:{line} depends on '{dependency}'"
                )
    assert not findings, (
        "Domain plugins must stay agnostic of the frontend mode (S152 R1):\n  - "
        + "\n  - ".join(findings)
    )


def test_theme_adapters_never_import_domain_plugins():
    findings: List[str] = []
    adapter_directories = [
        directory
        for directory in _plugin_directories()
        if directory.name.startswith(THEME_PREFIX + "_")
    ]
    assert (
        PLUGINS_DIRECTORY / THEME_PREFIX in _plugin_directories()
    ), "the walk does not find the theme plugin itself — it is broken"
    if not adapter_directories:
        pytest.skip("no theme_* adapter checked out next to theme (isolated CI)")
    for directory in adapter_directories:
        for file_path in _python_files(directory):
            for line, plugin_name in _imported_plugin_names(_parse(file_path)):
                if not plugin_name.startswith(THEME_PREFIX):
                    findings.append(
                        f"{_relative(file_path)}:{line} imports plugins.{plugin_name}"
                    )
    assert not findings, (
        "Theme adapters talk to domain plugins over HTTP only (S152 D3):\n  - "
        + "\n  - ".join(findings)
    )
