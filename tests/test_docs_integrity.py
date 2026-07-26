"""Integrity checks for the documentation set.

These replace a family of tests that asserted specific sentences appeared in
specific markdown files. Those pinned prose, not behaviour: they failed on any
rewording and passed even when a link pointed at a file that had been deleted.

What is worth enforcing is that the docs hang together -- every internal link
resolves, and the entry points a reader is told to use actually exist.
"""

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def _markdown_files():
    """Tracked markdown only.

    An rglob here would also collect files under gitignored directories, which
    makes the number of collected tests a property of the developer's working
    tree rather than of the repository -- a local scratch directory silently
    changes the suite size, and any "N passed" figure written down is then
    wrong on every other machine.
    """
    # -z keeps non-ASCII paths verbatim; without it git octal-escapes them and
    # wraps the whole name in quotes, so every Chinese filename here breaks.
    listed = subprocess.run(
        ["git", "ls-files", "-z", "*.md"],
        cwd=REPO_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=True,
    ).stdout
    return [REPO_ROOT / name for name in sorted(listed.split("\0")) if name.strip()]


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
