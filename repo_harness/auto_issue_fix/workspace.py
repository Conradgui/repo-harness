"""Git workspace, diff, and test helpers for Auto Issue Fix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .config import CommandResult
from .security import redact_text, require_ok, run_command

IGNORED_DIFF_PREFIXES = (".git/", ".repo-harness/", ".venv/", "venv/", "node_modules/")
IGNORED_DIFF_SUFFIXES = (".pyc",)


def infer_test_commands(repo_root: Path) -> tuple[str, ...]:
    if (repo_root / "pyproject.toml").exists() or (repo_root / "pytest.ini").exists():
        if (repo_root / "tests").exists():
            return ("python -m pytest -q",)
    if (repo_root / "package.json").exists():
        return ("npm test",)
    if (repo_root / "go.mod").exists():
        return ("go test ./...",)
    if (repo_root / "Cargo.toml").exists():
        return ("cargo test",)
    return ()


def run_shell_command(command: str, cwd: Path, timeout: int = 600) -> CommandResult:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        shell=True,
        timeout=timeout,
        check=False,
    )
    return CommandResult(
        args=(command,),
        cwd=str(cwd.resolve()),
        returncode=int(completed.returncode),
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )


def run_test_commands(commands: tuple[str, ...], cwd: Path, log_path: Path) -> list[dict]:
    results = []
    blocks = []
    for command in commands:
        result = run_shell_command(command, cwd=cwd)
        status = "passed" if result.ok else "failed"
        results.append({"command": command, "status": status, "returncode": result.returncode})
        blocks.append(
            redact_text(
                f"$ {command}\nreturncode: {result.returncode}\n\nSTDOUT\n{result.stdout}\n\nSTDERR\n{result.stderr}\n"
            )
        )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("\n\n".join(blocks) if blocks else "(no test command inferred or provided)\n", encoding="utf-8")
    return results


def _diff_base(cwd: Path) -> str | None:
    result = run_command(["git", "rev-parse", "--verify", "HEAD"], cwd=cwd)
    return "HEAD" if result.ok else None


def _untracked_paths(cwd: Path) -> tuple[str, ...]:
    result = run_command(["git", "ls-files", "--others", "--exclude-standard"], cwd=cwd)
    require_ok(result, "git ls-files --others failed")
    paths = []
    for line in result.stdout.splitlines():
        path = line.strip()
        normalized = path.replace("\\", "/")
        if path and not normalized.startswith(IGNORED_DIFF_PREFIXES) and "__pycache__/" not in normalized and not normalized.endswith(IGNORED_DIFF_SUFFIXES):
            paths.append(path)
    return tuple(paths)


def changed_paths(cwd: Path) -> tuple[str, ...]:
    base = _diff_base(cwd)
    args = ["git", "diff", "--name-only", base, "--"] if base else ["git", "diff", "--name-only", "--cached", "--"]
    result = run_command(args, cwd=cwd)
    require_ok(result, "git diff --name-only failed")
    paths = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    for path in _untracked_paths(cwd):
        if path not in paths:
            paths.append(path)
    return tuple(paths)


def _untracked_file_diff(cwd: Path, path: str) -> str:
    file_path = cwd / path
    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"diff --git a/{path} b/{path}\nnew file mode 100644\nBinary files /dev/null and b/{path} differ\n"
    lines = content.splitlines()
    hunk = [f"diff --git a/{path} b/{path}", "new file mode 100644", "--- /dev/null", f"+++ b/{path}", f"@@ -0,0 +1,{len(lines)} @@"]
    hunk.extend(f"+{line}" for line in lines)
    return "\n".join(hunk) + "\n"


def git_diff(cwd: Path) -> str:
    base = _diff_base(cwd)
    args = ["git", "diff", "--binary", base, "--"] if base else ["git", "diff", "--binary", "--cached", "--"]
    result = run_command(args, cwd=cwd)
    require_ok(result, "git diff failed")
    untracked = "".join(_untracked_file_diff(cwd, path) for path in _untracked_paths(cwd))
    return result.stdout + untracked


def scan_diff_gate(cwd: Path, paths: tuple[str, ...], diff_text: str) -> str:
    if not paths:
        return "no changed files"
    for path in paths:
        normalized = path.replace("\\", "/")
        if normalized.startswith(IGNORED_DIFF_PREFIXES):
            return f"diff gate blocked generated or internal path: {path}"
    base = _diff_base(cwd)
    args = ["git", "diff", "--check", base, "--"] if base else ["git", "diff", "--check", "--cached", "--"]
    diff_check = run_command(args, cwd=cwd)
    if not diff_check.ok:
        return "git diff --check failed"
    if redact_text(diff_text) != diff_text:
        return "secret-shaped content detected in diff"
    return ""
