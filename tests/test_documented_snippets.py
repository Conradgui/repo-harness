"""Python snippets published as evidence must actually run.

A stage gate found a snippet in the delivery report -- offered as the one piece
of evidence that "survives anyone's environment" -- that failed the moment it
was executed. Nobody had run it. It sat in the paragraph written to atone for
publishing unverified claims.

Compiling the snippet would not have caught it: the outer code parsed fine, and
the failure was in the child process it spawned. So marked blocks are *run*, in
a subprocess, with a timeout. That is the only check that would have caught the
defect it exists to prevent.

A marked snippet must **assert its own claim**. Exit code 0 is the whole
verification, so a snippet that merely prints something proves nothing; write
the `assert` that states what the reader is supposed to conclude. A snippet
demonstrating a defect will legitimately print a traceback from a background
thread -- that is the demonstration, and it is why stderr is not inspected.

Only mark a snippet that is hermetic and safe: no network, no writes outside a
temp directory, no dependence on this machine. Most documentation examples are
illustrative and should stay unmarked -- a marker is a claim that the snippet
is evidence, and evidence has to execute.

    <!-- verify:python -->
    ```python
    import subprocess
    ```
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

BLOCK = re.compile(
    r"<!--\s*verify:python\s*-->\s*\n```(?:python|py)\n(.*?)```",
    re.DOTALL,
)

BLOCKQUOTE = re.compile(r"^ {0,3}> ?", re.MULTILINE)


def _unquote(text):
    """Strip blockquote markers so a snippet inside a `>` block is still read."""
    return BLOCKQUOTE.sub("", text)


def _tracked_markdown():
    listed = subprocess.run(
        ["git", "ls-files", "-z", "*.md"],
        cwd=REPO_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=True,
    ).stdout
    # git lists files that are tracked but deleted from disk; skip those rather
    # than failing collection mid-deletion.
    paths = (REPO_ROOT / name for name in sorted(listed.split("\0")) if name.strip())
    return [path for path in paths if path.is_file()]


def _snippets():
    for path in _tracked_markdown():
        text = _unquote(path.read_text(encoding="utf-8"))
        rel = path.relative_to(REPO_ROOT).as_posix()
        for index, source in enumerate(BLOCK.findall(text), start=1):
            yield rel, index, source


SNIPPETS = list(_snippets())


@pytest.mark.skipif(not SNIPPETS, reason="no snippets are marked for verification")
@pytest.mark.parametrize(
    "doc,index,source",
    SNIPPETS,
    ids=[f"{d}#{i}" for d, i, _ in SNIPPETS],
)
def test_marked_snippet_runs(doc, index, source, tmp_path):
    script = tmp_path / "snippet.py"
    script.write_text(source, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60, check=False,
    )

    assert result.returncode == 0, (
        f"{doc} snippet {index} exits {result.returncode}. It is published as "
        f"evidence, so it has to run, and its assertions have to hold.\n"
        f"--- stderr ---\n{result.stderr.strip()[:1500]}"
    )
