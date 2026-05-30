import json

from repo_harness import FakeModelClient, RepoHarness, SessionStore, WorkspaceContext


def build_agent(tmp_path, outputs=None, **kwargs):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    return RepoHarness(
        model_client=FakeModelClient(outputs or []),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".repo-harness" / "sessions"),
        approval_policy="auto",
        **kwargs,
    )


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_context_usage_is_recorded_for_turn_report_and_session_events(tmp_path):
    agent = build_agent(tmp_path, ["<final>hello</final>"])

    assert agent.ask("hi") == "hello"

    report = json.loads((agent.current_run_dir / "report.json").read_text(encoding="utf-8"))
    usage = report["prompt_metadata"]["context_usage"]
    assert usage["estimation_method"] == "cjk_aware"
    assert usage["sections"]["current_request"]["chars"] == len("Current user request:\nhi")
    assert usage["total_estimated_tokens"] == sum(section["tokens"] for section in usage["sections"].values())
    assert any(event["event"] == "context_usage_recorded" for event in read_jsonl(agent.session_event_bus.path))


def test_history_records_turn_ids_and_manual_compact_shortens_future_history(tmp_path):
    agent = build_agent(tmp_path, ["<final>first</final>"])
    assert agent.ask("first request") == "first"
    for index in range(20):
        agent.record({"role": "user", "content": f"old request {index} " + ("x" * 100), "created_at": f"2026-05-18T10:{index:02d}:00+08:00"})
        agent.record({"role": "assistant", "content": f"old answer {index} " + ("y" * 100), "created_at": f"2026-05-18T10:{index:02d}:10+08:00"})

    before = agent.prompt("next")
    summary = agent.compact_history(trigger="manual")
    after = agent.prompt("next")

    assert all(item.get("turn_id") for item in agent.session["history"] if item.get("role") in {"user", "assistant", "tool"})
    assert summary["pre_tokens"] > summary["post_tokens"]
    assert len(after) < len(before)
    assert "Compacted session summary:" in after
    assert any(event["event"] == "compaction_created" for event in read_jsonl(agent.session_event_bus.path))
