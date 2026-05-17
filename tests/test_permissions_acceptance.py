import json

from repo_harness import FakeModelClient, RepoHarness, SessionStore, WorkspaceContext
from repo_harness.permissions import PermissionDecision
from repo_harness.sandbox import SandboxConfig


def build_agent(tmp_path, outputs=None, **kwargs):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    return RepoHarness(
        model_client=FakeModelClient(outputs or []),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".repo-harness" / "sessions"),
        **kwargs,
    )


def read_events(agent):
    return [json.loads(line) for line in agent.session_event_bus.path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_permission_checker_is_single_default_tool_gate(tmp_path):
    agent = build_agent(tmp_path, approval_policy="never")

    read_decision = agent.permission_checker.check("read_file", {"path": "README.md"})
    shell_decision = agent.permission_checker.check("run_shell", {"command": "echo hi", "timeout": 20})

    assert read_decision == PermissionDecision.allow("read_only")
    assert shell_decision == PermissionDecision.deny("approval_denied", security_event_type="approval_denied")
    result = agent.run_tool("run_shell", {"command": "echo hi", "timeout": 20})

    assert result == "error: approval denied for run_shell"
    assert agent._last_tool_result_metadata["tool_error_code"] == "approval_denied"
    assert any(event["event"] == "permission_decision" and event["decision"] == "deny" for event in read_events(agent))


def test_required_sandbox_fails_closed_after_permission(tmp_path):
    agent = build_agent(tmp_path, approval_policy="auto", sandbox_config=SandboxConfig(mode="required", backend="bubblewrap"))
    agent.sandbox_runner.which = lambda name: None

    result = agent.run_tool("run_shell", {"command": "echo hi", "timeout": 20})

    assert "sandbox required but unavailable" in result
    assert agent._last_tool_result_metadata["tool_error_code"] == "tool_failed"
    assert any(event["event"] == "sandbox_unavailable" for event in read_events(agent))
