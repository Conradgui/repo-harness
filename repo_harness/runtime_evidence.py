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
