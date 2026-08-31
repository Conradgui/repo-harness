"""Runtime evidence helpers for reports and task_state snapshots."""

import json
import re
from pathlib import Path

ROUTE_PATTERN = re.compile(r"(?<![A-Za-z0-9_])/(?:api/)?[A-Za-z0-9_./{}:-]+")


def artifact_graph(root, changed_paths):
    root = Path(root)
    paths = []
    route_refs = set()
    api_refs = set()
    category_hints = set()
    for item in changed_paths:
        path = str(item).replace("\\", "/")
        if path in paths:
            continue
        paths.append(path)
        suffix = Path(path).suffix.lower()
        if suffix in {".py", ".js", ".ts", ".tsx", ".jsx"}:
            category_hints.add("code")
        if "test" in Path(path).parts or Path(path).name.startswith("test_"):
            category_hints.add("tests")
        full_path = root / path
        if not full_path.is_file():
            continue
        try:
            text = full_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in ROUTE_PATTERN.findall(text):
            cleaned = match.rstrip(".,'\"`)]}")
            route_refs.add(cleaned)
            if cleaned.startswith("/api"):
                api_refs.add(cleaned)
    return {
        "changed_paths": paths,
        "route_refs": sorted(route_refs),
        "api_refs": sorted(api_refs),
        "category_hints": sorted(category_hints),
    }


def verifier_suggestions(root):
    root = Path(root)
    suggestions = []
    package_json = root / "package.json"
    if package_json.is_file():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        scripts = data.get("scripts", {}) if isinstance(data, dict) else {}
        if "test" in scripts:
            suggestions.append({"command": "npm test", "reason": "package.json defines a test script"})
        if "build" in scripts:
            suggestions.append({"command": "npm run build", "reason": "package.json defines a build script"})
    if (root / "tests").is_dir():
        suggestions.append({"command": "uv run python -m pytest -q", "reason": "Python tests directory exists"})
    return suggestions


VERIFICATION_RUNNER_HEADS = (
    "uv", "python", "python3", "pytest", "py.test", "ruff", "mypy",
    "eslint", "tsc", "npm", "yarn", "pnpm", "make", "go", "cargo",
    "gradle", "mvn", "dotnet", "tox", "nox", "vitest", "jest",
)
VERIFICATION_KEYWORDS = (
    "pytest", "unittest", "vitest", "jest", "ruff", "mypy", "eslint",
    "tsc", "test", "check", "lint", "build",
)


def is_verification_command(command):
    """判定一条 shell 命令是否是验证类命令。

    头命令（管道/链式第一段的首词）必须是常见 runner，且整条命令带验证
    关键词。echo/printf/cat 之类哑命令即使提到 pytest 也不算——完成验证
    门拦的是"没有真实验证"，不是"没提到验证"。
    """
    text = str(command or "").strip().lower()
    if not text:
        return False
    head = re.split(r"\||&&|;", text)[0].strip().split()
    if not head or head[0] not in VERIFICATION_RUNNER_HEADS:
        return False
    return any(keyword in text for keyword in VERIFICATION_KEYWORDS)


def final_verification_notice(changed_paths, verification_attempts, root):
    """act 模式完成验证门：返回 None 可 finish，返回字符串为拦截 notice。

    本 turn 有文件改动、且改动之后没有任何验证命令时，final 不得进入
    success 终态——与 plan 模式 can_finish() 对称的完成门。改动作废既有
    验证证据（见 tool_executor 的记录时序），所以这里只需检查证据非空。
    """
    changed = list(changed_paths or [])
    attempts = list(verification_attempts or [])
    if not changed or attempts:
        return None
    suggestions = [item.get("command", "") for item in verifier_suggestions(root)]
    hint = suggestions[0] if suggestions else "uv run python -m pytest -q"
    return (
        f"This run changed {len(changed)} file(s) but no verification command ran after "
        f"the changes. Run a relevant verification command (e.g. `{hint}`) and address "
        "failures before declaring the task complete."
    )
