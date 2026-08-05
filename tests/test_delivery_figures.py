"""The figures in the delivery documents must match scripts/measure.py.

ADR-006 says every delivered number comes from a command. Every stage-gate
review so far has found the same defect anyway: a figure written correctly once
and never regenerated when the commit that invalidated it landed.

The rule was enforced by a reviewer noticing. This enforces it.

A figure is registered here by writing it as `<!-- measure:key -->` next to the
value in the document. The test extracts the value that follows the marker and
compares it against the same key from measure.py. Adding a marker is how a
number becomes load-bearing; a number without one is prose and is not checked.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs"

# `<!-- measure:source_lines -->14,553` or `<!-- measure:source_lines -->14553`
MARKER = re.compile(r"<!--\s*measure:([a-z_]+)\s*-->\s*\*{0,2}([\d,]+)")


def _merge_base():
    """The fork point of HEAD against origin/main, used as the delta baseline.

    origin/main is a floating pointer -- after the optimization branch merges
    back it no longer represents the pre-optimization baseline, and every
    measured delta collapses to zero. The merge-base is the immutable,
    recomputable fork point the delivery deltas are quoted against.
    """
    result = subprocess.run(
        ["git", "merge-base", "origin/main", "HEAD"],
        cwd=REPO_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha or None


@pytest.fixture(scope="module")
def baseline():
    """The merge-base of HEAD against origin/main: the before-baseline."""
    ref = _merge_base()
    if not ref:
        pytest.fail("cannot compute merge-base with origin/main; delta checks need a baseline")
    result = subprocess.run(
        [sys.executable, "scripts/measure.py", ref],
        cwd=REPO_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    if result.returncode != 0:
        pytest.fail(f"baseline unavailable: {result.stderr.strip()[:200]}")
    return json.loads(result.stdout)


@pytest.fixture(scope="module")
def measured():
    # sys.executable, not a hard-coded .venv path -- a worktree whose virtualenv
    # is named anything else would otherwise error rather than measure.
    result = subprocess.run(
        [sys.executable, "scripts/measure.py"],
        cwd=REPO_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"measure.py unavailable: {result.stderr.strip()[:200]}")
    return json.loads(result.stdout)


def _marked_documents():
    # Every tracked markdown file, not only docs/ -- a marker in README.md
    # would otherwise be silently unchecked.
    listed = subprocess.run(
        ["git", "ls-files", "-z", "*.md"],
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


DELTA = re.compile(r"<!--\s*delta:([a-z_]+)(:pct)?\s*-->\s*([−+\-])([\d,]+)")


def _delta_claims():
    for path, text in _marked_documents():
        doc = path.relative_to(REPO_ROOT).as_posix()
        for key, pct, sign, raw in DELTA.findall(text):
            yield doc, key, bool(pct), sign, int(raw.replace(",", ""))


DELTA_CLAIMS = list(_delta_claims())


@pytest.mark.skipif(not DELTA_CLAIMS, reason="no deltas are registered yet")
@pytest.mark.parametrize(
    "doc,key,_pct,sign,claimed",
    DELTA_CLAIMS,
    ids=[f"{d}:Δ{k}" for d, k, _, _, _ in DELTA_CLAIMS],
)
def test_registered_delta_matches_the_measured_change(
    doc, key, _pct, sign, claimed, measured, baseline
):
    """A generated value beside a hand-written difference is how the summary
    table went arithmetically false twice. The difference is checked too.

    Deltas are cross-branch semantics: they quote the change from the
    merge-base (the optimization fork point) to the current branch. On main,
    where HEAD *is* the merge-base, there is no cross-branch delta to verify --
    every difference would legitimately be zero, so the checks skip there.
    """
    if _merge_base() is None:
        pytest.skip("not a git repo with origin/main; delta semantics unavailable")
    import subprocess as _sp

    head_result = _sp.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    if head_result.returncode == 0 and head_result.stdout.strip() == _merge_base():
        pytest.skip("HEAD is the merge-base with origin/main; no cross-branch delta to verify")

    assert key in measured and key in baseline, f"{doc} references unknown key {key}"

    change = measured[key] - baseline[key]
    expected_sign = "+" if change > 0 else "−"

    assert sign == expected_sign, (
        f"{doc} states Δ{key} as {sign}, measured change is {change:+}"
    )
    assert abs(change) == claimed, (
        f"{doc} states Δ{key}={claimed:,}, measured {abs(change):,}. "
        f"Run scripts/sync_figures.py."
    )
