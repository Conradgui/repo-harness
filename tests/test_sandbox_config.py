from repo_harness import FakeModelClient, RepoHarness, SessionStore, WorkspaceContext
from repo_harness.sandbox import SandboxConfig


def build_agent(tmp_path, sandbox_config):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    return RepoHarness(
        model_client=FakeModelClient([]),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".repo-harness" / "sessions"),
        approval_policy="auto",
        sandbox_config=sandbox_config,
    )


def test_required_sandbox_does_not_honor_excluded_commands(tmp_path):
    agent = build_agent(
        tmp_path,
        SandboxConfig(mode="required", backend="bubblewrap", excluded_commands=("echo*",)),
    )
    agent.sandbox_runner.which = lambda name: None

    result = agent.run_tool("run_shell", {"command": "echo hi", "timeout": 20})

    assert "sandbox required but unavailable" in result


def test_best_effort_excluded_commands_support_glob_patterns(tmp_path):
    agent = build_agent(
        tmp_path,
        SandboxConfig(mode="best_effort", backend="bubblewrap", excluded_commands=("python*",)),
    )
    agent.sandbox_runner.which = lambda name: None

    result = agent.run_tool("run_shell", {"command": "python --version", "timeout": 20})

    assert "sandbox_unavailable" not in agent.session_event_bus.path.read_text(encoding="utf-8")
    assert "exit_code:" in result

