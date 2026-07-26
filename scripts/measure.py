"""Measure the repository the same way every time.

Every figure quoted in docs/delivery/ comes from this script. Numbers written
by hand drifted: the delivery report ended up comparing a raw line count at one
commit against a non-blank count at another, and reported the difference as if
both were the same measurement.

Usage:
    python scripts/measure.py              # measure the working tree
    python scripts/measure.py <git-ref>    # measure a ref via a temp worktree
"""

import ast
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _run(args, cwd):
    return subprocess.run(
        args, cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )


def _tracked_python(root, prefix):
    """Tracked .py files under prefix. Uses git so untracked scratch never counts."""
    out = _run(["git", "ls-files", f"{prefix}/*.py"], root).stdout
    return [root / line for line in out.splitlines() if line.strip()]


def _line_count(paths):
    """Raw physical lines -- the definition used everywhere in the delivery docs."""
    total = 0
    for path in paths:
        if path.is_file():
            total += len(path.read_text(encoding="utf-8", errors="replace").splitlines())
    return total


def _ruff_errors(root):
    ruff = REPO / ".venv" / "Scripts" / "ruff.exe"
    if not ruff.is_file():
        ruff = Path(shutil.which("ruff") or "ruff")
    result = _run([str(ruff), "check", str(root)], root)
    for line in (result.stdout + result.stderr).splitlines():
        if line.startswith("Found ") and "error" in line:
            return int(line.split()[1])
    return 0


def _largest_class(root):
    path = root / "repo_harness" / "runtime.py"
    if not path.is_file():
        return {}
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "RepoHarness":
            methods = [n for n in node.body if isinstance(n, ast.FunctionDef)]
            return {"methods": len(methods), "class_lines": node.end_lineno - node.lineno + 1}
    return {}


def measure(root):
    source = _tracked_python(root, "repo_harness")
    tests = _tracked_python(root, "tests")
    return {
        "source_lines": _line_count(source),
        "source_files": len(source),
        "test_lines": _line_count(tests),
        "test_files": len(tests),
        "ruff_errors": _ruff_errors(root),
        **_largest_class(root),
    }


def main():
    if len(sys.argv) > 1:
        ref = sys.argv[1]
        with tempfile.TemporaryDirectory(prefix="rh-measure-") as tmp:
            target = Path(tmp) / "tree"
            add = _run(["git", "worktree", "add", "--detach", str(target), ref], REPO)
            if add.returncode != 0:
                print(add.stderr.strip(), file=sys.stderr)
                return 1
            try:
                result = measure(target)
            finally:
                _run(["git", "worktree", "remove", str(target), "--force"], REPO)
        result["ref"] = ref
    else:
        result = measure(REPO)
        result["ref"] = "working tree"

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
