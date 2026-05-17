from unittest.mock import patch

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


def test_sandbox_read_only_blocks_run_shell_before_subprocess(tmp_path):
    agent = build_agent(tmp_path, SandboxConfig(mode="read_only", backend="native"))

    with patch("repo_harness.tools.subprocess.run") as fake_run:
        result = agent.run_tool("run_shell", {"command": "echo hi", "timeout": 20})

    assert "sandbox read_only blocks run_shell" in result
    fake_run.assert_not_called()
    assert agent._last_tool_result_metadata["tool_status"] == "error"


def test_sandbox_config_resolves_from_repo_harness_toml(tmp_path):
    (tmp_path / ".repo-harness.toml").write_text(
        "[sandbox]\nmode = \"best_effort\"\nbackend = \"native\"\n",
        encoding="utf-8",
    )
    args = type(
        "Args",
        (),
        {
            "cwd": str(tmp_path),
            "provider": "openai",
            "_provider_explicit": False,
            "model": None,
            "_model_explicit": False,
            "base_url": None,
            "_base_url_explicit": False,
            "config": None,
            "max_steps": None,
            "_max_steps_explicit": False,
            "max_new_tokens": None,
            "_max_new_tokens_explicit": False,
            "sandbox": None,
            "sandbox_backend": None,
        },
    )()

    from repo_harness.config import resolve_runtime_config

    config = resolve_runtime_config(args, WorkspaceContext.build(tmp_path))

    assert config.sandbox.mode == "best_effort"
    assert config.sandbox.backend == "native"


def test_sandbox_required_rejects_when_backend_unavailable(tmp_path):
    agent = build_agent(tmp_path, SandboxConfig(mode="required", backend="bubblewrap"))
    agent.sandbox_runner.which = lambda name: None

    result = agent.run_tool("run_shell", {"command": "echo hi", "timeout": 20})

    assert "sandbox required but unavailable" in result
    assert agent._last_tool_result_metadata["tool_error_code"] == "tool_failed"


def test_best_effort_records_degrade_and_runs_without_backend(tmp_path):
    agent = build_agent(tmp_path, SandboxConfig(mode="best_effort", backend="bubblewrap"))
    agent.sandbox_runner.which = lambda name: None

    result = agent.run_tool("run_shell", {"command": "echo hi", "timeout": 20})

    assert "exit_code: 0" in result
    assert "hi" in result
    assert "sandbox_unavailable" in agent.session_event_bus.path.read_text(encoding="utf-8")
