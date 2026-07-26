"""Integrity checks for the documentation set.

These replace a family of tests that asserted specific sentences appeared in
specific markdown files. Those pinned prose, not behaviour: they failed on any
rewording and passed even when a link pointed at a file that had been deleted.

What is worth enforcing is that the docs hang together -- every internal link
resolves, and the entry points a reader is told to use actually exist.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules", ".pytest_cache"}


def _markdown_files():
    for path in sorted(REPO_ROOT.rglob("*.md")):
        if any(part in SKIP_DIRS for part in path.relative_to(REPO_ROOT).parts):
            continue
        yield path


def _internal_targets(path):
    """Yield (raw_link, resolved_path) for links that point inside the repo."""
    for raw in MARKDOWN_LINK.findall(path.read_text(encoding="utf-8")):
        link = raw.strip()
        if link.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target = link.split("#", 1)[0].split("?", 1)[0]
        if not target:
            continue
        yield link, (path.parent / target).resolve()


@pytest.mark.parametrize(
    "doc", [pytest.param(p, id=p.relative_to(REPO_ROOT).as_posix()) for p in _markdown_files()]
)
def test_internal_links_resolve(doc):
    broken = [
        link
        for link, resolved in _internal_targets(doc)
        if not resolved.exists()
    ]

    assert broken == [], f"{doc.relative_to(REPO_ROOT)} links to missing paths: {broken}"


def test_readme_points_at_the_getting_started_guide():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "docs/getting-started.md" in readme
    assert (REPO_ROOT / "docs" / "getting-started.md").is_file()


def test_documented_cli_entry_points_are_declared_in_packaging():
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    guide = (REPO_ROOT / "docs" / "getting-started.md").read_text(encoding="utf-8")

    # The guide tells readers to run `repo-harness`; packaging must ship it.
    assert "repo-harness" in guide
    assert 'repo-harness = "repo_harness.cli:main"' in pyproject


def test_no_markdown_file_is_empty():
    empty = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in _markdown_files()
        if not path.read_text(encoding="utf-8").strip()
    ]

    assert empty == []
