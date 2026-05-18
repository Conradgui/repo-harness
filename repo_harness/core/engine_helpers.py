"""Helper routines for Engine control-loop side effects."""

import time

from ..providers.base import complete_model
from ..providers.errors import ProviderError
from ..workspace import clip, now


def execute_tool_payload(engine, task_state, user_message, payload):
    agent = engine.runtime
    name = payload.get("name", "")
    args = payload.get("args", {})
    task_state.record_tool(name)
    tool_started_at = time.monotonic()
    agent.session_event_bus.emit("tool_started", {"run_id": task_state.run_id, "tool_name": name, "args": args})
    yield {"type": "tool_call", "run_id": task_state.run_id, "name": name, "args": args}

    tool_result = agent.run_tool(name, args)
    tool_metadata = dict(agent._last_tool_result_metadata or {})
    tool_duration_ms = int((time.monotonic() - tool_started_at) * 1000)
    agent.session_event_bus.emit(
        "tool_finished",
        {
            "run_id": task_state.run_id,
            "tool_name": name,
            "status": tool_metadata.get("tool_status", ""),
            "tool_error_code": tool_metadata.get("tool_error_code", ""),
            "workspace_changed": bool(tool_metadata.get("workspace_changed", False)),
            "affected_paths": list(tool_metadata.get("affected_paths", [])),
            "duration_ms": tool_duration_ms,
        },
    )
    agent.record({"role": "tool", "name": name, "args": args, "content": tool_result, "created_at": now()})
    for notification in engine.drain_worker_notifications():
        yield {"type": "worker_notification", "run_id": getattr(agent, "current_run_id", ""), "content": notification}
    agent.run_store.write_task_state(task_state)
    agent.emit_trace(
        task_state,
        "tool_executed",
        {
            "name": name,
            "tool_name": name,
            "args": args,
            "result": clip(tool_result, 500),
            "duration_ms": tool_duration_ms,
            "artifact_paths": list(tool_metadata.get("affected_paths", [])),
            **tool_metadata,
        },
    )
    checkpoint = agent.create_checkpoint(task_state, user_message, trigger="tool_executed")
    agent.run_store.write_task_state(task_state)
    agent.emit_trace(task_state, "checkpoint_created", {"checkpoint_id": checkpoint["checkpoint_id"], "trigger": "tool_executed"})
    yield {"type": "tool_result", "run_id": task_state.run_id, "name": name, "content": tool_result, "metadata": tool_metadata}


def finish_stopped_run(engine, task_state, user_message, final, stop_reason, run_started_at):
    agent = engine.runtime
    task_state.stop(stop_reason, final_answer=final)
    agent.abort_requested = False
    agent.record({"role": "assistant", "content": final, "created_at": now()})
    agent.session_event_bus.emit("assistant_message", {"run_id": task_state.run_id, "kind": "stop", "content": clip(final, 500)})
    agent.run_store.write_task_state(task_state)
    checkpoint = agent.create_checkpoint(task_state, user_message, trigger=stop_reason)
    agent.emit_trace(task_state, "checkpoint_created", {"checkpoint_id": checkpoint["checkpoint_id"], "trigger": stop_reason})
    agent.emit_trace(
        task_state,
        "run_finished",
        {
            "status": task_state.status,
            "stop_reason": task_state.stop_reason,
            "final_answer": final,
            "run_duration_ms": int((time.monotonic() - run_started_at) * 1000),
        },
    )
    agent.session_event_bus.emit(
        "turn_finished",
        {
            "run_id": task_state.run_id,
            "status": task_state.status,
            "stop_reason": task_state.stop_reason,
            "duration_ms": int((time.monotonic() - run_started_at) * 1000),
        },
    )
    agent.run_store.write_report(task_state, agent.redact_artifact(agent.build_report(task_state)))
    agent.current_turn_id = ""
    agent.current_run_id = ""
    yield {"type": "stop", "run_id": task_state.run_id, "content": final}
    yield {"type": "turn_finished", "run_id": task_state.run_id, "status": task_state.status, "stop_reason": task_state.stop_reason}


def finish_limited_run(engine, task_state, user_message, final, run_started_at):
    agent = engine.runtime
    agent.record({"role": "assistant", "content": final, "created_at": now()})
    agent.session_event_bus.emit("assistant_message", {"run_id": task_state.run_id, "kind": "stop", "content": clip(final, 500)})
    agent.promote_durable_memory(user_message, final)
    maintain_memory_safely(agent, task_state, final)
    agent._finalize_runtime_evidence(task_state)
    agent.run_store.write_task_state(task_state)
    checkpoint = agent.create_checkpoint(task_state, user_message, trigger=task_state.stop_reason or "run_stopped")
    agent.emit_trace(task_state, "checkpoint_created", {"checkpoint_id": checkpoint["checkpoint_id"], "trigger": task_state.stop_reason or "run_stopped"})
    agent.emit_trace(
        task_state,
        "run_finished",
        {
            "status": task_state.status,
            "stop_reason": task_state.stop_reason,
            "final_answer": final,
            "run_duration_ms": int((time.monotonic() - run_started_at) * 1000),
        },
    )
    agent.session_event_bus.emit(
        "turn_finished",
        {
            "run_id": task_state.run_id,
            "status": task_state.status,
            "stop_reason": task_state.stop_reason,
            "duration_ms": int((time.monotonic() - run_started_at) * 1000),
        },
    )
    agent.run_store.write_report(task_state, agent.redact_artifact(agent.build_report(task_state)))
    agent.current_turn_id = ""
    agent.current_run_id = ""
    yield {"type": "stop", "run_id": task_state.run_id, "content": final}
    yield {"type": "turn_finished", "run_id": task_state.run_id, "status": task_state.status, "stop_reason": task_state.stop_reason}


def should_retry_model_error(exc, provider_retries):
    if not isinstance(exc, ProviderError):
        return False
    code = str(getattr(exc, "code", "") or "")
    if code not in {"empty_response"}:
        return False
    return provider_retries.get(code, 0) < 1


def maintain_memory_safely(agent, task_state, final_answer):
    try:
        if hasattr(agent, "maintain_memory_after_turn"):
            agent.maintain_memory_after_turn(final_answer)
        else:
            agent.run_memory_self_iteration()
    except Exception as exc:
        audit = getattr(agent, "last_memory_maintenance", {"errors": []})
        errors = audit.setdefault("errors", [])
        errors.append(str(exc))
        agent.last_memory_maintenance = audit
        agent.session_event_bus.emit("memory_maintenance_failed", {"run_id": task_state.run_id, "error": clip(str(exc), 300)})
        agent.emit_trace(task_state, "memory_maintenance_failed", {"error": clip(str(exc), 300)})


_STEP_LIMIT_SUMMARY_NOTICE = (
    "You have hit the per-turn tool budget (max_steps). Do not call any more tools. "
    "Return one <final>...</final> answer in the user's language that briefly covers: "
    "what was accomplished, what remains undone, and how the user can continue."
)


def request_step_limit_summary(engine, task_state, user_message):
    agent = engine.runtime
    started_at = time.monotonic()
    try:
        prompt, _ = agent._build_prompt_and_metadata(_STEP_LIMIT_SUMMARY_NOTICE)
        result = complete_model(agent.model_client, prompt, agent.max_new_tokens)
    except Exception as exc:
        agent.emit_trace(task_state, "step_limit_summary_failed", {"error": clip(str(exc), 200)})
        return None
    raw = (result.text or "").strip() if result else ""
    kind, payload = agent.parse(raw)
    duration_ms = int((time.monotonic() - started_at) * 1000)
    agent.emit_trace(task_state, "step_limit_summary", {"kind": kind, "duration_ms": duration_ms, "produced": bool(kind == "final")})
    if kind == "final" and payload:
        return str(payload).strip()
    return None
