import json

from repo_harness import FakeModelClient, RepoHarness, SessionStore, WorkspaceContext


def build_agent(tmp_path, outputs):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    return RepoHarness(
        model_client=FakeModelClient(outputs),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".repo-harness" / "sessions"),
        approval_policy="auto",
    )


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_runtime_evidence_graph_and_verifier_suggestions_are_reported(tmp_path):
    (tmp_path / "package.json").write_text('{"scripts":{"test":"vitest run","build":"vite build"}}\n', encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_smoke.py").write_text("def test_smoke():\n    assert True\n", encoding="utf-8")
    agent = build_agent(
        tmp_path,
        [
            '<tool>{"name":"write_file","args":{"path":"src/api.py","content":"@app.get(\\"/api/items\\")\\ndef list_items():\\n    return fetch(\\"/api/users\\")\\n"}}</tool>',
            "<final>Wrote API file.</final>",
        ],
    )

    assert agent.ask("add api") == "Wrote API file."
    report = json.loads((agent.current_run_dir / "report.json").read_text(encoding="utf-8"))
    task_state = json.loads((agent.current_run_dir / "task_state.json").read_text(encoding="utf-8"))

    assert report["artifact_graph"]["changed_paths"] == ["src/api.py"]
    assert "/api/items" in report["artifact_graph"]["route_refs"]
    assert "/api/users" in report["artifact_graph"]["api_refs"]
    assert task_state["artifact_graph"] == report["artifact_graph"]
    commands = [item["command"] for item in report["verifier_suggestions"]]
    assert "npm test" in commands
    assert "npm run build" in commands
    assert "uv run python -m pytest -q" in commands
    tool_event = next(event for event in read_jsonl(agent.current_run_dir / "trace.jsonl") if event["event"] == "tool_executed")
    assert tool_event["phase"] == "tool"
    assert tool_event["turn_id"] == agent.current_task_state.task_id
    assert tool_event["artifact_paths"] == ["src/api.py"]
    assert tool_event["span_id"]


def test_runtime_reminder_records_failed_tool_without_breaking_turn(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            '<tool>{"name":"patch_file","args":{"path":"missing.py","old_text":"x","new_text":"y"}}</tool>',
            "<final>Could not patch.</final>",
        ],
    )

    assert agent.ask("patch missing") == "Could not patch."
    report = json.loads((agent.current_run_dir / "report.json").read_text(encoding="utf-8"))
    assert report["runtime_reminders"]
    assert report["runtime_reminders"][-1]["tool"] == "patch_file"
    assert json.loads((agent.current_run_dir / "task_state.json").read_text(encoding="utf-8"))["runtime_reminders"] == report["runtime_reminders"]
