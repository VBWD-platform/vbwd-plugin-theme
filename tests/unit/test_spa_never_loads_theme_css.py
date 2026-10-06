"""S152 R9 — the Vue SPA never loads the theme stylesheet (no bridge; tokens shared by name).

Scans the fe-user checkout next to vbwd-backend (``vbwd-sdk/vbwd-fe-user``) for
references to the theme asset routes. The plugin's own CI clones only
vbwd-backend, so the guard skips there with a reason.
"""
from pathlib import Path
from typing import List

import pytest

FORBIDDEN_REFERENCES = (b"/_render/_theme", b"theme.css")
EXCLUDED_DIRECTORY_NAMES = frozenset({"node_modules", "tests", ".git"})
BACKEND_ROOT = Path(__file__).resolve().parents[4]
FE_USER_ROOT = BACKEND_ROOT.parent / "vbwd-fe-user"


def _scanned_files(fe_user_root: Path) -> List[Path]:
    roots = [fe_user_root / "vue" / "src"] + sorted(
        path for path in (fe_user_root / "plugins").glob("*") if path.is_dir()
    )
    files = [
        fe_user_root / "index.html",
        fe_user_root / "vue" / "index.html",
    ]
    for root in roots:
        files.extend(
            path
            for path in root.rglob("*")
            if path.is_file()
            and not EXCLUDED_DIRECTORY_NAMES.intersection(
                path.relative_to(fe_user_root).parts
            )
        )
    return [path for path in files if path.is_file()]


def theme_stylesheet_references(fe_user_root: Path) -> List[str]:
    """``<relative path>: <reference>`` for every forbidden reference found."""
    findings = []
    for path in _scanned_files(fe_user_root):
        content = path.read_bytes()
        for reference in FORBIDDEN_REFERENCES:
            if reference in content:
                relative_path = path.relative_to(fe_user_root)
                findings.append(f"{relative_path}: {reference.decode()}")
    return findings


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_scanner_reports_references_and_honours_the_exclusions(tmp_path):
    _write(tmp_path / "vue" / "src" / "main.ts", "import '/_render/_theme/public/x';")
    _write(tmp_path / "vue" / "index.html", '<link href="/theme.css">')
    _write(tmp_path / "plugins" / "shop" / "index.ts", "load('theme.css')")
    _write(tmp_path / "plugins" / "shop" / "tests" / "x.spec.ts", "theme.css")
    _write(tmp_path / "plugins" / "shop" / "node_modules" / "a" / "b.js", "theme.css")
    _write(tmp_path / "plugins" / "shop" / "clean.ts", "export const ok = 1;")

    assert sorted(theme_stylesheet_references(tmp_path)) == [
        "plugins/shop/index.ts: theme.css",
        "vue/index.html: theme.css",
        "vue/src/main.ts: /_render/_theme",
    ]


def test_spa_assets_never_reference_theme_css():
    if not (FE_USER_ROOT / "vue" / "src").is_dir():
        pytest.skip(f"fe-user checkout not present at {FE_USER_ROOT} (plugin-only CI)")

    assert theme_stylesheet_references(FE_USER_ROOT) == []
