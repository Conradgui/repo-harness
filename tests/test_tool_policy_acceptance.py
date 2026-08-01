import json
import shlex
import sys

from repo_harness import FakeModelClient, RepoHarness, SessionStore, WorkspaceContext


def build_agent(tmp_path, outputs=None, **kwargs):
    (tmp_path / "README.md").write_text("hello world\n", encoding="utf-8")
    return RepoHarness(
        model_client=FakeModelClient(outputs or []),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".repo-harness" / "sessions"),
        approval_policy="auto",
        **kwargs,
    )


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_shell_sequence_read_commands_are_rejected_and_emit_policy_event(tmp_path):
    agent = build_agent(tmp_path)

    rejected = agent.run_tool("run_shell", {"command": "echo ok; cat README.md", "timeout": 20})

    assert "search" in rejected or "read_file" in rejected
    assert agent._last_tool_result_metadata["tool_error_code"] == "shell_search_should_use_tool"
    assert any(
        event["event"] == "tool_policy_decision"
        and event["tool_name"] == "run_shell"
        and event["decision"] == "deny"
        for event in read_jsonl(agent.session_event_bus.path)
    )


def test_self_authored_new_file_can_be_patched_without_extra_read(tmp_path):
    agent = build_agent(tmp_path)

    assert agent.run_tool("write_file", {"path": "scripts/check.py", "content": "assert False\n"}) == "wrote scripts/check.py (13 chars)"
    patched = agent.run_tool(
        "patch_file",
        {"path": "scripts/check.py", "old_text": "assert False", "new_text": "assert True"},
    )

    assert patched == "patched scripts/check.py"
    assert (tmp_path / "scripts" / "check.py").read_text(encoding="utf-8") == "assert True\n"


def test_long_shell_output_is_clipped_and_full_output_is_saved_as_run_artifact(tmp_path):
    script = "print('x'*6000)"
    command = f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"
    agent = build_agent(
        tmp_path,
        [
            f'<tool>{{"name":"run_shell","args":{{"command":{json.dumps(command)},"timeout":20}}}}</tool>',
            "<final>captured</final>",
        ],
    )

    assert agent.ask("produce long shell output") == "captured"

    tool_item = next(item for item in agent.session["history"] if item["role"] == "tool" and item["name"] == "run_shell")
    assert len(tool_item["content"]) < 1400
    assert "full output saved:" in tool_item["content"]
    artifact_path = agent._last_tool_result_metadata["full_output_artifact"]
    assert artifact_path
    assert "x" * 6000 in (tmp_path / artifact_path).read_text(encoding="utf-8")
    assert any(event.get("full_output_artifact") == artifact_path for event in read_jsonl(agent.current_run_dir / "trace.jsonl"))


def test_multiple_tool_calls_execute_in_order_and_record_partial_failure(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            '<tool>{"name":"write_file","args":{"path":"first.txt","content":"one\\n"}}</tool>'
            '<tool>{"name":"run_shell","args":{"command":"python -c \\"import sys; sys.exit(3)\\"","timeout":20}}</tool>'
            '<tool>{"name":"write_file","args":{"path":"second.txt","content":"two\\n"}}</tool>',
            "<final>multi done</final>",
        ],
    )

    assert agent.ask("run multiple tools") == "multi done"

    tool_history = [item for item in agent.session["history"] if item["role"] == "tool"]
    assert [item["name"] for item in tool_history] == ["write_file", "run_shell", "write_file"]
    assert (tmp_path / "first.txt").read_text(encoding="utf-8") == "one\n"
    assert (tmp_path / "second.txt").read_text(encoding="utf-8") == "two\n"
    trace = read_jsonl(agent.current_run_dir / "trace.jsonl")
    failed_shell = next(event for event in trace if event.get("event") == "tool_executed" and event.get("tool_name") == "run_shell")
    assert failed_shell["tool_status"] == "error"
    assert failed_shell["tool_error_code"] == "tool_failed"


def test_run_shell_success_reports_ok_status(tmp_path):
    """Exit code 0 maps to tool_status='ok' with no error code."""
    agent = build_agent(tmp_path)

    result = agent.run_tool("run_shell", {"command": "echo ok", "timeout": 20})

    assert "exit_code: 0" in result
    assert agent._last_tool_result_metadata["tool_status"] == "ok"
    assert agent._last_tool_result_metadata["tool_error_code"] == ""


def test_run_shell_failure_with_workspace_change_reports_partial_success(tmp_path):
    """A command that writes a file AND exits non-zero maps to partial_success."""
    script = "open('partial.txt','w').write('data'); import sys; sys.exit(1)"
    command = f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"
    agent = build_agent(tmp_path)

    result = agent.run_tool("run_shell", {"command": command, "timeout": 20})

    assert "exit_code: 1" in result
    assert (tmp_path / "partial.txt").read_text(encoding="utf-8") == "data"
    meta = agent._last_tool_result_metadata
    assert meta["tool_status"] == "partial_success"
    assert meta["tool_error_code"] == "tool_partial_success"
    assert meta["workspace_changed"] is True
    assert "partial.txt" in meta["affected_paths"]


def test_run_shell_long_output_without_task_state_is_clipped_without_artifact(tmp_path):
    """Long output outside an ask() cycle is clipped but not saved to disk."""
    script = "print('y'*6000)"
    command = f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"
    agent = build_agent(tmp_path)

    result = agent.run_tool("run_shell", {"command": command, "timeout": 20})

    assert len(result) < 1400
    assert agent._last_tool_result_metadata["full_output_artifact"] == ""
    assert "full output saved:" not in result
