from repo_harness import FakeModelClient, RepoHarness, SessionStore, WorkspaceContext
from repo_harness import cli as mini_cli


def build_agent(tmp_path, outputs=None):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    return RepoHarness(
        model_client=FakeModelClient(outputs or []),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".repo-harness" / "sessions"),
        approval_policy="auto",
    )


def test_usage_and_model_commands_are_runtime_only_and_redacted(tmp_path):
    agent = build_agent(tmp_path, ["<final>ok</final>"])
    agent.model_client.model = "old-model"
    agent.model_client.base_url = "https://example.com/v1?api_key=secret#frag"
    agent.model_client.last_completion_metadata = {
        "provider_protocol": "openai",
        "provider_attempts": 2,
        "provider_retry_count": 1,
        "input_tokens": 10,
        "output_tokens": 3,
    }
    assert agent.ask("hello") == "ok"

    handled, _, output = mini_cli.handle_repl_command(agent, "/model new-model")
    assert handled is True
    assert output == "model: new-model"
    assert agent.model_client.model == "new-model"
    assert not (tmp_path / ".repo-harness.toml").exists()

    handled, _, output = mini_cli.handle_repl_command(agent, "/usage")
    assert handled is True
    assert "model: new-model" in output
    assert "provider protocol: openai" in output
    assert "provider attempts: 2" in output
    assert "api_key" not in output
    assert "secret" not in output


def test_history_context_working_memory_and_compact_commands(tmp_path):
    agent = build_agent(tmp_path, ["<final>done</final>"])
    assert agent.ask("first") == "done"

    for index in range(16):
        agent.record({"role": "user", "content": f"old request {index} " + ("x" * 80), "created_at": f"2026-05-18T10:{index:02d}:00+08:00"})
        agent.record({"role": "assistant", "content": f"old answer {index} " + ("y" * 80), "created_at": f"2026-05-18T10:{index:02d}:10+08:00"})

    for command, required in [
        ("/history", agent.session["id"]),
        ("/context", "context_usage"),
        ("/working-memory", "Working memory"),
        ("/compact", "pre_tokens"),
    ]:
        handled, _, output = mini_cli.handle_repl_command(agent, command)
        assert handled is True
        assert required in output

    assert agent.session.get("compactions")
