"""Measure the repository the same way every time.

Every figure quoted in docs/delivery/ and docs/decisions/ comes from here.
Hand-written numbers drifted twice: the delivery report once compared a raw
line count at one commit against a non-blank count at another and reported the
difference as if both were the same measurement, and a later correction pass
introduced nine fresh figures that could not be recomputed.

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

# Modules whose size is quoted in the delivery documents.
QUOTED_MODULES = (
    "repo_harness/runtime.py",
    "repo_harness/cli.py",
    "repo_harness/memory.py",
    "repo_harness/memory_pack.py",
    "repo_harness/context_manager.py",
    "repo_harness/metrics.py",
    "repo_harness/evaluator.py",
    "repo_harness/release_evidence.py",
    "repo_harness/core/engine.py",
)


class MeasurementError(RuntimeError):
    """Raised when a figure cannot be established. Never return a default."""


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
    """Raw physical lines -- the definition used everywhere in the docs."""
    total = 0
    for path in paths:
        if path.is_file():
            total += len(path.read_text(encoding="utf-8", errors="replace").splitlines())
    return total


def _ruff_errors(root):
    """Error count from ruff. Raises rather than reporting a clean run it did not see."""
    ruff = REPO / ".venv" / "Scripts" / "ruff.exe"
    if not ruff.is_file():
        found = shutil.which("ruff")
        if not found:
            raise MeasurementError("ruff not found; cannot measure lint")
        ruff = Path(found)
    result = _run([str(ruff), "check", str(root)], root)
    output = result.stdout + result.stderr
    for line in output.splitlines():
        if line.startswith("Found ") and "error" in line:
            return int(line.split()[1])
    if "All checks passed" in output:
        return 0
    raise MeasurementError(
        f"could not parse ruff output (exit {result.returncode}): {output.strip()[:400]}"
    )


def _bucket(name):
    n = name.lstrip("_")
    if "memory" in n or n in {"remember", "remember_candidate"}:
        return "memory"
    if "worker" in n or n.startswith("spawn") or "subagent" in n:
        return "worker"
    if "prefix" in n or "prompt" in n or n == "build_tools":
        return "prompt"
    if "checkpoint" in n or "resume" in n:
        return "checkpoint"
    if "skill" in n:
        return "skills"
    if "plan" in n:
        return "plan"
    if n.startswith("tool_") or "tool" in n:
        return "tool-proxy"
    if "metric" in n or "usage" in n or "token" in n or "compact" in n or "context" in n:
        return "metrics/context"
    return "core"


def _runtime_class(root):
    path = root / "repo_harness" / "runtime.py"
    if not path.is_file():
        raise MeasurementError("repo_harness/runtime.py missing")
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "RepoHarness":
            methods = [n for n in node.body if isinstance(n, ast.FunctionDef)]
            clusters = {}
            for m in methods:
                key = _bucket(m.name)
                entry = clusters.setdefault(key, {"methods": 0, "lines": 0})
                entry["methods"] += 1
                entry["lines"] += m.end_lineno - m.lineno + 1
            forwarders = [
                m.name for m in methods
                if m.name.startswith("tool_")
                and len(m.body) == 1
                and isinstance(m.body[0], ast.Return)
            ]
            return {
                "runtime_methods": len(methods),
                "runtime_class_lines": node.end_lineno - node.lineno + 1,
                "runtime_clusters": dict(sorted(clusters.items(), key=lambda kv: -kv[1]["lines"])),
                "tool_forwarders": len(forwarders),
            }
    raise MeasurementError("class RepoHarness not found")


def _engine_class(root):
    path = root / "repo_harness" / "core" / "engine.py"
    if not path.is_file():
        raise MeasurementError("core/engine.py missing")
    text = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Engine":
            return {
                "engine_file_lines": len(text.splitlines()),
                "engine_class_lines": node.end_lineno - node.lineno + 1,
            }
    raise MeasurementError("class Engine not found")


def _module_lines(root):
    out = {}
    for rel in QUOTED_MODULES:
        path = root / rel
        out[rel] = (
            len(path.read_text(encoding="utf-8", errors="replace").splitlines())
            if path.is_file() else None
        )
    return out


def _merge_base(root):
    """The fork point where HEAD diverged from origin/main.

    origin/main is a floating pointer: once the optimization branch merges back,
    it stops representing the pre-optimization baseline, and every measured
    delta collapses to zero (observed on macOS/main). The merge-base is the
    immutable, recomputable fork point the delivery deltas are measured against.
    """
    result = _run(["git", "merge-base", "origin/main", "HEAD"], root)
    sha = result.stdout.strip()
    if result.returncode != 0 or not sha:
        raise MeasurementError(
            f"cannot compute merge-base with origin/main: {result.stderr.strip()[:200]}"
        )
    return sha


def _commit_stats(root):
    base = _merge_base(root)
    count = _run(["git", "rev-list", "--count", f"{base}..HEAD"], root).stdout.strip()
    return {
        "commits_ahead_of_main": int(count) if count.isdigit() else None,
        "baseline_sha": base,
    }


def measure(root, with_commits=True):
    source = _tracked_python(root, "repo_harness")
    tests = _tracked_python(root, "tests")
    result = {
        "source_lines": _line_count(source),
        "source_files": len(source),
        "test_lines": _line_count(tests),
        "test_files": len(tests),
        "ruff_errors": _ruff_errors(root),
        **_runtime_class(root),
        **_engine_class(root),
        "module_lines": _module_lines(root),
    }
    if with_commits:
        result.update(_commit_stats(root))
    return result


def main():
    try:
        if len(sys.argv) > 1:
            ref = sys.argv[1]
            with tempfile.TemporaryDirectory(prefix="rh-measure-") as tmp:
                target = Path(tmp) / "tree"
                add = _run(["git", "worktree", "add", "--detach", str(target), ref], REPO)
                if add.returncode != 0:
                    raise MeasurementError(add.stderr.strip())
                try:
                    result = measure(target, with_commits=False)
                finally:
                    _run(["git", "worktree", "remove", str(target), "--force"], REPO)
            result["ref"] = ref
        else:
            result = measure(REPO)
            result["ref"] = "working tree"
    except MeasurementError as exc:
        print(f"measurement failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
