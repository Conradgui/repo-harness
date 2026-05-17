import json

from repo_harness import FakeModelClient, RepoHarness, SessionStore, WorkspaceContext
from repo_harness import cli as mini_cli


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


def test_plan_mode_allows_only_active_plan_artifact_and_blocks_final_until_written(tmp_path):
    bad = '<tool>{"name":"write_file","args":{"path":"src.py","content":"print(1)\\n"}}</tool>'
    good = '<tool>{"name":"write_file","args":{"path":".repo-harness/plans/cache-plan.md","content":"# Plan\\n- Inspect cache.\\n"}}</tool>'
    agent = build_agent(tmp_path, [bad, "<final>Too early.</final>", good, "<final>Plan ready.</final>"], max_steps=6)

    plan_path = agent.enter_plan_mode("cache")
    answer = agent.ask("make a plan")

    assert plan_path == ".repo-harness/plans/cache-plan.md"
    assert answer == "Plan ready."
    assert not (tmp_path / "src.py").exists()
    assert (tmp_path / ".repo-harness" / "plans" / "cache-plan.md").read_text(encoding="utf-8").startswith("# Plan")
    assert agent.runtime_mode == "default"
    trace = read_jsonl(agent.current_run_dir / "trace.jsonl")
    assert any(event.get("tool_error_code") == "plan_mode_path_mismatch" for event in trace)
    assert any(event.get("event") == "runtime_notice" and "Plan mode requires" in event.get("content", "") for event in trace)


def test_plan_commands_report_mode_and_reject_bad_path(tmp_path):
    agent = build_agent(tmp_path)

    handled, should_exit, output = mini_cli.handle_repl_command(agent, "/plan refactor")
    assert handled is True and should_exit is False
    assert ".repo-harness/plans/refactor-plan.md" in output
    assert agent.runtime_mode == "plan"

    handled, _, output = mini_cli.handle_repl_command(agent, "/mode")
    assert handled is True
    assert "runtime mode: plan" in output

    handled, _, output = mini_cli.handle_repl_command(agent, "/plan bad ../escape.md")
    assert handled is True
    assert "plan mode already active" in output

    handled, _, output = mini_cli.handle_repl_command(agent, "/plan-exit")
    assert handled is True
    assert "runtime mode: default" in output
