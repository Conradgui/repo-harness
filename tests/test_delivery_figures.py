"""The figures in the delivery documents must match scripts/measure.py.

ADR-006 says every delivered number comes from a command. Four stage-gate
reviews have now found the same defect anyway: a figure written correctly once
and never regenerated when the commit that invalidated it landed. Gates 1-4
returned 14, 9, 10 and 6 findings, most of them this.

The rule was enforced by a reviewer noticing. This enforces it.

A figure is registered here by writing it as `<!-- measure:key -->` next to the
value in the document. The test extracts the value that follows the marker and
compares it against the same key from measure.py. Adding a marker is how a
number becomes load-bearing; a number without one is prose and is not checked.
"""

import json
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs"

# `<!-- measure:source_lines -->14,553` or `<!-- measure:source_lines -->14553`
MARKER = re.compile(r"<!--\s*measure:([a-z_]+)\s*-->\s*\*{0,2}([\d,]+)")


@pytest.fixture(scope="module")
def measured():
    result = subprocess.run(
        [str(REPO_ROOT / ".venv" / "Scripts" / "python.exe"), "scripts/measure.py"],
        cwd=REPO_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"measure.py unavailable: {result.stderr.strip()[:200]}")
    return json.loads(result.stdout)


def _marked_documents():
    listed = subprocess.run(
        ["git", "ls-files", "-z", "docs/*.md"],
        cwd=REPO_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=True,
    ).stdout
    for name in sorted(listed.split("\0")):
        if not name.strip():
            continue
        path = REPO_ROOT / name
        text = path.read_text(encoding="utf-8")
        if MARKER.search(text):
            yield path, text


def _claims():
    for path, text in _marked_documents():
        for key, raw in MARKER.findall(text):
            yield path.relative_to(REPO_ROOT).as_posix(), key, int(raw.replace(",", ""))


CLAIMS = list(_claims())


@pytest.mark.skipif(not CLAIMS, reason="no measured figures are registered yet")
@pytest.mark.parametrize(
    "doc,key,claimed",
    CLAIMS,
    ids=[f"{d}:{k}" for d, k, _ in CLAIMS],
)
def test_registered_figure_matches_the_script(doc, key, claimed, measured):
    assert key in measured, f"{doc} references measure key '{key}', which the script does not emit"

    assert measured[key] == claimed, (
        f"{doc} states {key}={claimed:,}, but scripts/measure.py reports "
        f"{measured[key]:,}. Regenerate the figure rather than editing this test."
    )


def test_every_measure_marker_names_a_real_key(measured):
    unknown = {key for _, key, _ in CLAIMS if key not in measured}

    assert unknown == set(), f"markers reference keys measure.py does not emit: {sorted(unknown)}"
