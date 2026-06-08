"""Tool execution guardrail used by the RepoHarness runtime."""

import re

from ..tools import _normalize_tool_args
from ..workspace import clip

INLINE_TOOL_OUTPUT_LIMIT = 1000


def run_tool(agent, name, args):
    tool = agent.tools.get(name)
    if tool is None:
        agent._last_tool_result_metadata = _metadata(
            "rejected",
            "unknown_tool",
            risk_level="high",
            read_only=False,
        )
        agent._record_runtime_reminder(name, agent._last_tool_result_metadata)
        return f"error: unknown tool '{name}'"
    try:
        args = _normalize_tool_args(name, args or {})
        agent.validate_tool(name, args)
    except Exception as exc:
        example = agent.tool_example(name)
        message = f"error: invalid arguments for {name}: {exc}"
        if example:
            message += f"\nexample: {example}"
        security_event_type = "path_escape" if "path escapes workspace" in str(exc) else ""
        agent._last_tool_result_metadata = _metadata(
            "rejected",
            "invalid_arguments",
            security_event_type=security_event_type,
            risk_level=_risk(tool),
            read_only=_read_only(tool),
        )
        agent._record_runtime_reminder(name, agent._last_tool_result_metadata)
        return message
    if agent.repeated_tool_call(name, args):
        agent._last_tool_result_metadata = _metadata(
            "rejected",
            "repeated_identical_call",
            security_event_type="tool_policy",
            risk_level=_risk(tool),
            read_only=_read_only(tool),
        )
        agent.record_process_note_for_tool(name, agent._last_tool_result_metadata)
        agent._record_runtime_reminder(name, agent._last_tool_result_metadata)
        _emit_tool_policy_decision(agent, name, args, "deny", "repeated_identical_call")
        return f"error: repeated identical tool call for {name}; choose a different tool or return a final answer"

    decision = agent.permission_checker.check(tool, args)
    _emit_permission_decision(agent, tool, args, decision)
    if not decision.allowed:
        agent._last_tool_result_metadata = _metadata(
            "rejected",
            decision.reason,
            security_event_type=decision.security_event_type,
            risk_level=_risk(tool),
            read_only=_read_only(tool),
        )
        agent.record_process_note_for_tool(name, agent._last_tool_result_metadata)
        agent._record_runtime_reminder(name, agent._last_tool_result_metadata)
        return _permission_error(agent, tool, decision)

    policy = agent.tool_policy.decision(name, args)
    _emit_tool_policy_decision(agent, name, args, policy.decision, policy.reason)
    if not policy.allowed:
        agent._last_tool_result_metadata = _metadata(
            "rejected",
            policy.reason,
            security_event_type="tool_policy",
            risk_level=_risk(tool),
            read_only=_read_only(tool),
        )
        agent.record_process_note_for_tool(name, agent._last_tool_result_metadata)
        agent._record_runtime_reminder(name, agent._last_tool_result_metadata)
        return policy.message

    if _risky(tool) and not agent.approve(name, args):
        agent._last_tool_result_metadata = _metadata(
            "rejected",
            "approval_denied",
            security_event_type="read_only_block" if agent.read_only else "approval_denied",
            risk_level="high",
            read_only=False,
        )
        agent._record_runtime_reminder(name, agent._last_tool_result_metadata)
        return f"error: approval denied for {name}"

    before_snapshot = agent.capture_workspace_snapshot() if _risky(tool) else {}
    after_snapshot = before_snapshot
    try:
        full_result = _execute(tool, args)
        result, full_output_artifact = _render_tool_result(agent, name, full_result)
        after_snapshot = agent.capture_workspace_snapshot() if _risky(tool) else before_snapshot
        affected_paths, diff_summary = agent.diff_workspace_snapshots(before_snapshot, after_snapshot)
        workspace_changed = bool(affected_paths)
        tool_status = "ok"
        tool_error_code = ""
        if name == "run_shell":
            match = re.search(r"exit_code:\s*(-?\d+)", result)
            exit_code = int(match.group(1)) if match else 0
            if exit_code != 0 and workspace_changed:
                tool_status = "partial_success"
                tool_error_code = "tool_partial_success"
            elif exit_code != 0:
                tool_status = "error"
                tool_error_code = "tool_failed"
        agent.update_memory_after_tool(name, args, result)
        agent._last_tool_result_metadata = _metadata(
            tool_status,
            tool_error_code,
            risk_level=_risk(tool),
            read_only=_read_only(tool),
            affected_paths=affected_paths,
            workspace_changed=workspace_changed,
            workspace_fingerprint=agent.workspace.fingerprint(),
            diff_summary=diff_summary,
            full_output_artifact=full_output_artifact,
        )
        if affected_paths:
            agent._run_changed_paths.extend(path for path in affected_paths if path not in agent._run_changed_paths)
        agent.record_process_note_for_tool(name, agent._last_tool_result_metadata)
        agent.tool_policy.record_result(name, args, agent._last_tool_result_metadata)
        if tool_status not in {"ok"}:
            agent._record_runtime_reminder(name, agent._last_tool_result_metadata)
        return result
    except Exception as exc:
        after_snapshot = agent.capture_workspace_snapshot() if _risky(tool) else before_snapshot
        affected_paths, diff_summary = agent.diff_workspace_snapshots(before_snapshot, after_snapshot)
        workspace_changed = bool(affected_paths)
        security_event_type = "path_escape" if "path escapes workspace" in str(exc) else ""
        agent._last_tool_result_metadata = _metadata(
            "partial_success" if workspace_changed else "error",
            "tool_partial_success" if workspace_changed else "tool_failed",
            security_event_type=security_event_type,
            risk_level=_risk(tool),
            read_only=_read_only(tool),
            affected_paths=affected_paths,
            workspace_changed=workspace_changed,
            workspace_fingerprint=agent.workspace.fingerprint(),
            diff_summary=diff_summary,
        )
        agent.record_process_note_for_tool(name, agent._last_tool_result_metadata)
        agent._record_runtime_reminder(name, agent._last_tool_result_metadata)
        return f"error: tool {name} failed: {exc}"


def _execute(tool, args):
    if hasattr(tool, "execute"):
        result = tool.execute(args)
        return getattr(result, "content", result)
    return tool["run"](args)


def _render_tool_result(agent, name, full_result):
    full_result = str(full_result)
    if name != "run_shell" or len(full_result) <= INLINE_TOOL_OUTPUT_LIMIT:
        return clip(full_result), ""
    if not getattr(agent, "current_task_state", None):
        return clip(full_result, INLINE_TOOL_OUTPUT_LIMIT), ""
    path = agent.run_store.write_text_artifact(agent.current_task_state, f"{name}-output", full_result)
    relative = path.relative_to(agent.root).as_posix()
    return f"full output saved: {relative}\n" + clip(full_result, INLINE_TOOL_OUTPUT_LIMIT), relative


def _emit_permission_decision(agent, tool, args, decision):
    agent.session_event_bus.emit(
        "permission_decision",
        {
            "tool_name": _name(tool),
            "tool": _name(tool),
            "decision": decision.decision,
            "reason": decision.reason,
            "security_event_type": decision.security_event_type,
            "tool_profile": decision.profile,
            "profile": decision.profile,
            "args": args or {},
        },
    )


def _emit_tool_policy_decision(agent, name, args, decision, reason):
    agent.session_event_bus.emit(
        "tool_policy_decision",
        {"tool_name": name, "decision": decision, "reason": reason, "args": args or {}},
    )


def _permission_error(agent, tool, decision):
    name = _name(tool)
    if decision.reason == "plan_mode_path_mismatch":
        return f"error: plan mode only allows writing the active plan artifact: {agent.active_plan_path}"
    if decision.reason == "plan_mode_tool_not_allowed":
        return f"error: plan mode only allows read-only tools or writing the active plan artifact: {agent.active_plan_path}"
    if decision.reason == "write_scope_mismatch":
        return f"error: worker write_scope does not allow {name} on this path"
    if decision.reason in {"approval_denied", "tool_not_allowed"}:
        return f"error: approval denied for {name}"
    return f"error: {decision.reason}"


def _metadata(
    tool_status,
    tool_error_code,
    *,
    security_event_type="",
    risk_level="low",
    read_only=True,
    affected_paths=None,
    workspace_changed=False,
    workspace_fingerprint="",
    diff_summary=None,
    full_output_artifact="",
):
    return {
        "tool_status": tool_status,
        "tool_error_code": tool_error_code,
        "security_event_type": security_event_type,
        "risk_level": risk_level,
        "read_only": read_only,
        "affected_paths": list(affected_paths or []),
        "workspace_changed": bool(workspace_changed),
        "workspace_fingerprint": workspace_fingerprint,
        "diff_summary": list(diff_summary or []),
        "full_output_artifact": full_output_artifact,
    }


def _name(tool):
    return getattr(tool, "name", "")


def _risky(tool):
    return bool(getattr(tool, "risky", tool.get("risky", False) if isinstance(tool, dict) else False))


def _read_only(tool):
    return bool(getattr(tool, "read_only", not _risky(tool)))


def _risk(tool):
    return "high" if _risky(tool) else "low"
