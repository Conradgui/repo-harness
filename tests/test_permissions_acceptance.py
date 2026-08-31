import json
from pathlib import Path
from unittest.mock import patch

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


def test_ask_approval_prompts_once_for_risky_tool(tmp_path):
    agent = build_agent(tmp_path, approval_policy="ask")

    with patch("builtins.input", return_value="y") as mock_input:
        result = agent.run_tool("write_file", {"path": "approved.txt", "content": "ok\n"})

    assert result == "wrote approved.txt (3 chars)"
    assert mock_input.call_count == 1


def test_write_file_into_runtime_state_dir_is_denied(tmp_path):
    """Model tools must not write harness state under .repo-harness/.

    Durable memory, sessions, run records and review queues are governance
    data whose only writers are harness modules. A tool write there bypasses
    the review queue and secret filtering, and the polluted notes would be
    fed back into every later prompt through memory recall.
    """
    agent = build_agent(tmp_path, approval_policy="auto")

    result = agent.run_tool(
        "write_file",
        {"path": ".repo-harness/memory/topics/injected.md", "content": "- injected note\n"},
    )

    assert "harness-owned runtime state" in result
    assert agent._last_tool_result_metadata["tool_status"] == "rejected"
    assert agent._last_tool_result_metadata["tool_error_code"] == "runtime_state_write_denied"
    assert not (tmp_path / ".repo-harness" / "memory" / "topics" / "injected.md").exists()
    assert any(
        event["event"] == "permission_decision"
        and event["decision"] == "deny"
        and event["security_event_type"] == "state_dir_write_guard"
        for event in read_events(agent)
    )


def test_patch_file_into_runtime_state_dir_is_denied(tmp_path):
    agent = build_agent(tmp_path, approval_policy="auto")
    topic = tmp_path / ".repo-harness" / "memory" / "topics" / "real.md"
    topic.parent.mkdir(parents=True, exist_ok=True)
    topic.write_text("## Notes\n- original\n", encoding="utf-8")

    result = agent.run_tool(
        "patch_file",
        {
            "path": ".repo-harness/memory/topics/real.md",
            "old_text": "original",
            "new_text": "tampered",
        },
    )

    assert "harness-owned runtime state" in result
    assert topic.read_text(encoding="utf-8") == "## Notes\n- original\n"


def test_runtime_state_dir_guard_survives_path_normalization(tmp_path):
    agent = build_agent(tmp_path, approval_policy="auto")

    dotdot = agent.run_tool(
        "write_file",
        {"path": ".repo-harness/../.repo-harness/memory/topics/x.md", "content": "x"},
    )
    absolute = agent.run_tool(
        "write_file",
        {"path": str(tmp_path / ".repo-harness" / "sessions" / "forged.json"), "content": "{}"},
    )

    assert "harness-owned runtime state" in dotdot
    assert "harness-owned runtime state" in absolute
    assert not (tmp_path / ".repo-harness" / "memory" / "topics" / "x.md").exists()
    assert not (tmp_path / ".repo-harness" / "sessions" / "forged.json").exists()


def test_runtime_state_dir_guard_overrides_write_scope(tmp_path):
    agent = build_agent(tmp_path, approval_policy="auto", write_scope=(".repo-harness/memory",))

    result = agent.run_tool(
        "write_file",
        {"path": ".repo-harness/memory/topics/scope-bypass.md", "content": "x"},
    )

    assert "harness-owned runtime state" in result
    assert not (tmp_path / ".repo-harness" / "memory" / "topics" / "scope-bypass.md").exists()


def test_runtime_state_dir_guard_blocks_symlink_into_state_dir(tmp_path):
    agent = build_agent(tmp_path, approval_policy="auto")
    state_dir = tmp_path / ".repo-harness" / "memory"
    state_dir.mkdir(parents=True, exist_ok=True)
    link = tmp_path / "alias-topic.md"
    link.symlink_to(state_dir / "topics.md")

    result = agent.run_tool("write_file", {"path": "alias-topic.md", "content": "injected"})

    assert "harness-owned runtime state" in result
    assert not (state_dir / "topics.md").exists()


def test_plan_mode_plan_artifact_write_not_affected_by_state_dir_guard(tmp_path):
    agent = build_agent(tmp_path, approval_policy="auto")
    agent.enter_plan_mode("wire the gate")

    result = agent.run_tool(
        "write_file",
        {"path": agent.active_plan_path, "content": "# plan\n- step\n"},
    )

    assert result.startswith("wrote ")
    assert (tmp_path / agent.active_plan_path).exists()


def test_regular_workspace_writes_not_affected_by_state_dir_guard(tmp_path):
    agent = build_agent(tmp_path, approval_policy="auto")

    result = agent.run_tool("write_file", {"path": "src/main.py", "content": "print('ok')\n"})

    assert result == "wrote src/main.py (12 chars)"
    assert (tmp_path / "src" / "main.py").exists()


def test_runtime_state_dir_read_is_not_blocked_by_write_guard(tmp_path):
    agent = build_agent(tmp_path)
    topic = tmp_path / ".repo-harness" / "memory" / "topics" / "note.md"
    topic.parent.mkdir(parents=True, exist_ok=True)
    topic.write_text("## Notes\n- durable note\n", encoding="utf-8")

    decision = agent.permission_checker.check(
        "read_file", {"path": ".repo-harness/memory/topics/note.md"}
    )
    result = agent.run_tool("read_file", {"path": ".repo-harness/memory/topics/note.md"})

    assert decision.allowed
    assert "durable note" in result


def test_runtime_state_dir_guard_resolves_symlinked_workspace_root(tmp_path):
    """The guard must not depend on the caller resolving runtime.root.

    An unresolved symlinked root (e.g. /var -> /private/var on macOS) makes
    every state-dir path compare unequal, and the guard silently approves
    the write. permission_probe.py exposed exactly this on its mkdtemp root.
    """
    from repo_harness.permissions import PermissionChecker

    real = tmp_path / "real"
    real.mkdir()
    (real / ".repo-harness").mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real)

    class MinimalRuntime:
        root = alias
        tools = {}
        active_tool_profile = None
        tool_profile = "default"
        runtime_mode = "default"
        write_scope = ()
        read_only = False
        approval_policy = "auto"
        sandbox_config = None

        def path(self, raw):
            return (Path(self.root) / str(raw)).resolve()

    decision = PermissionChecker(MinimalRuntime()).check(
        "write_file", {"path": ".repo-harness/memory/topics/x.md"}
    )

    assert decision.allowed is False
    assert decision.reason == "runtime_state_write_denied"
def test_approval_escalation_for_write_tools_is_path_bound(tmp_path):
    """Answering a(llow) must bind to the approved path, not the tool name.

    Approving one write_file does not approve writing every other file for
    the rest of the session; a different path re-enters approval.
    """
    agent = build_agent(tmp_path, approval_policy="ask")

    answers = iter(["a", "y"])
    with patch("builtins.input", side_effect=lambda *a, **k: next(answers)) as mock_input:
        first = agent.run_tool("write_file", {"path": "approved.txt", "content": "1\n"})
        second = agent.run_tool("write_file", {"path": "other.txt", "content": "2\n"})

    assert first == "wrote approved.txt (2 chars)"
    assert second == "wrote other.txt (2 chars)"
    assert mock_input.call_count == 2


def test_approved_write_path_repeats_without_prompting(tmp_path):
    agent = build_agent(tmp_path, approval_policy="ask")

    with patch("builtins.input", return_value="a"):
        agent.run_tool("write_file", {"path": "approved.txt", "content": "1\n"})

    agent.run_tool("read_file", {"path": "approved.txt"})
    with patch("builtins.input") as no_more_prompts:
        no_more_prompts.side_effect = AssertionError("same path should not re-prompt")
        result = agent.run_tool("write_file", {"path": "approved.txt", "content": "3\n"})

    assert result == "wrote approved.txt (2 chars)"
    assert no_more_prompts.call_count == 0


def test_approval_escalation_emits_audit_event(tmp_path):
    agent = build_agent(tmp_path, approval_policy="ask")

    with patch("builtins.input", return_value="a"):
        agent.run_tool("write_file", {"path": "approved.txt", "content": "1\n"})

    assert any(
        event["event"] == "approval_escalated" and event["path"] == "approved.txt"
        for event in read_events(agent)
    )


def test_run_shell_has_no_session_wide_escalation(tmp_path):
    """Every command is approved on its own; 'a' never covers future commands.

    Approving one command string must not approve whatever the model sends
    next -- there is no argument boundary broad enough to make that safe.
    """
    agent = build_agent(tmp_path, approval_policy="ask")

    answers = iter(["a", "y"])
    with patch("builtins.input", side_effect=lambda *a, **k: next(answers)) as mock_input:
        first = agent.run_tool("run_shell", {"command": "echo one", "timeout": 5})
        second = agent.run_tool("run_shell", {"command": "echo two", "timeout": 5})

    assert "exit_code: 0" in first
    assert "exit_code: 0" in second
    assert mock_input.call_count == 2


def test_approval_escalation_does_not_cross_tools(tmp_path):
    agent = build_agent(tmp_path, approval_policy="ask")

    answers = iter(["a", "y"])
    with patch("builtins.input", side_effect=lambda *a, **k: next(answers)) as mock_input:
        agent.run_tool("write_file", {"path": "approved.txt", "content": "1\n"})
        agent.run_tool("patch_file", {"path": "approved.txt", "old_text": "1", "new_text": "2"})

    assert mock_input.call_count == 2


def test_approval_prompt_shows_full_command_and_path(tmp_path):
    """The approval prompt must show decisive arguments untruncated.

    An 80-char json.dumps slice used to cut commands mid-flight, so the user
    approved something they never saw.
    """
    agent = build_agent(tmp_path, approval_policy="ask")
    long_command = (
        "uv run --with pytest python -m pytest "
        "tests/test_permissions_acceptance.py -q --tb=short -p no:cacheprovider"
    )
    deep_path = "src/very/deeply/nested/package/module_with_long_name.py"

    prompts = []
    with patch("builtins.input", side_effect=_record_and_refuse(prompts)):
        agent.run_tool("run_shell", {"command": long_command, "timeout": 5})
        agent.run_tool("write_file", {"path": deep_path, "content": "x"})

    assert long_command in prompts[0]
    assert deep_path in prompts[1]


def _record_and_refuse(prompts):
    def _inner(prompt=""):
        prompts.append(prompt)
        return "n"

    return _inner


def test_untrust_command_clears_session_escalations(tmp_path):
    agent = build_agent(tmp_path, approval_policy="ask")

    with patch("builtins.input", return_value="a"):
        agent.run_tool("write_file", {"path": "approved.txt", "content": "1\n"})

    from repo_harness.cli import handle_repl_command

    handled, _, output = handle_repl_command(agent, "/untrust")

    assert handled
    assert "approved.txt" in output
    agent.run_tool("read_file", {"path": "approved.txt"})
    with patch("builtins.input", return_value="y") as mock_input:
        agent.run_tool("write_file", {"path": "approved.txt", "content": "2\n"})

    assert mock_input.call_count == 1
