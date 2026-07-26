from unittest.mock import patch

import pytest

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

    # The refusal now comes from PermissionChecker, which reaches the decision
    # before SandboxRunner is consulted. Two things improve: the model gets a
    # named reason instead of a generic tool failure, and the status is
    # "rejected" rather than "error" -- a policy decision, not a malfunction.
    # SandboxRunner still raises for a direct call; see the next test.
    assert "sandbox_read_only" in result
    fake_run.assert_not_called()
    assert agent._last_tool_result_metadata["tool_status"] == "rejected"


def _must_not_run(command, timeout):
    raise AssertionError(f"the command must not reach the platform runner: {command!r}")


@pytest.mark.parametrize(
    "command",
    [
        "echo hi",
        "git status",                # matches the exclusion pattern exactly
        "git status/../whoami",      # git dashed-external dispatch
        "git status; rm -rf x",
    ],
)
def test_sandbox_runner_raises_on_read_only_mode(tmp_path, command):
    """read_only refuses before the exemption is consulted.

    excluded_commands is configured here on purpose. Without it this test
    passes under either ordering, and the ordering is the whole point: the
    exemption used to come first, so `git status/../whoami` ran unsandboxed.
    See ADR-007.
    """
    from repo_harness.sandbox import SandboxRunner

    config = SandboxConfig(
        mode="read_only", backend="native", excluded_commands=("git status*",)
    )
    runner = SandboxRunner(config)
    agent = build_agent(tmp_path, config)

    with pytest.raises(RuntimeError, match="sandbox read_only blocks run_shell"):
        runner.run(agent, command, 20, _must_not_run)


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
