"""Worker artifact helpers."""

import json
from pathlib import Path


def collect_worker_artifacts(runtime):
    run_dir = getattr(runtime, "current_run_dir", None)
    if not run_dir:
        return {}
    run_dir = Path(run_dir)
    payload = {
        "run_dir": _relative(runtime, run_dir),
        "report_path": _relative(runtime, run_dir / "report.json"),
        "trace_path": _relative(runtime, run_dir / "trace.jsonl"),
        "task_state_path": _relative(runtime, run_dir / "task_state.json"),
        "session_event_path": _relative(runtime, getattr(runtime.session_event_bus, "path", "")),
        "tool_error_codes": _tool_error_codes(run_dir / "trace.jsonl"),
    }
    return payload


def worker_artifacts(worker_manager):
    return worker_manager.to_dict()


def _tool_error_codes(trace_path):
    path = Path(trace_path)
    if not path.is_file():
        return []
    codes = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event") == "tool_executed":
            code = str(event.get("tool_error_code") or "")
            if code:
                codes.append(code)
    return codes


def _relative(runtime, path):
    if not path:
        return ""
    path = Path(path)
    try:
        return path.relative_to(runtime.root).as_posix()
    except ValueError:
        return str(path)
