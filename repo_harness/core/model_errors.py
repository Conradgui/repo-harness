"""Model error handling for Engine."""

from ..providers.errors import ProviderError
from ..workspace import clip, now


def finish_model_error(
    engine,
    task_state,
    user_message,
    prompt_metadata,
    exc,
    model_duration_ms,
    run_duration_ms,
):
    agent = engine.runtime
    metadata = _provider_error_metadata(exc)
    prompt_metadata = dict(prompt_metadata or {})
    prompt_metadata["provider_error"] = metadata
    agent.last_prompt_metadata = prompt_metadata
    agent.last_completion_metadata = {"provider_error": metadata}
    final = _format_provider_error(metadata)
    task_state.stop_model_error(final)
    agent.record({"role": "assistant", "content": final, "created_at": now()})
    agent.session_event_bus.emit(
        "model_error",
        {
            "run_id": task_state.run_id,
            "code": metadata.get("code", ""),
            "http_status": metadata.get("http_status"),
            "retry_count": metadata.get("retry_count", 0),
            "duration_ms": model_duration_ms,
        },
    )
    agent.session_event_bus.emit(
        "assistant_message",
        {"run_id": task_state.run_id, "kind": "model_error", "content": final},
    )
    agent.emit_trace(
        task_state,
        "model_error",
        {"error": metadata, "duration_ms": model_duration_ms, "status": "failed"},
    )
    agent.run_store.write_task_state(task_state)
    checkpoint = agent.create_checkpoint(task_state, user_message, trigger="model_error")
    agent.emit_trace(
        task_state,
        "checkpoint_created",
        {"checkpoint_id": checkpoint["checkpoint_id"], "trigger": "model_error"},
    )
    agent.emit_trace(
        task_state,
        "run_finished",
        {
            "status": task_state.status,
            "stop_reason": task_state.stop_reason,
            "final_answer": final,
            "run_duration_ms": run_duration_ms,
        },
    )
    agent.session_event_bus.emit(
        "turn_finished",
        {
            "run_id": task_state.run_id,
            "status": task_state.status,
            "stop_reason": task_state.stop_reason,
            "duration_ms": int(run_duration_ms or 0),
        },
    )
    agent.run_store.write_report(task_state, agent.redact_artifact(agent.build_report(task_state)))
    agent.current_turn_id = ""
    agent.current_run_id = ""
    yield {"type": "stop", "run_id": task_state.run_id, "content": final}
    yield {
        "type": "turn_finished",
        "run_id": task_state.run_id,
        "status": task_state.status,
        "stop_reason": task_state.stop_reason,
    }


def _provider_error_metadata(exc):
    if isinstance(exc, ProviderError):
        return exc.to_metadata()
    return {
        "message": clip(str(exc), 500),
        "provider": "",
        "model": "",
        "base_url": "",
        "code": type(exc).__name__,
        "http_status": None,
        "retryable": False,
        "attempts": 1,
        "retry_count": 0,
    }


def _format_provider_error(metadata):
    code = str(metadata.get("code", "") or "provider_error")
    status = metadata.get("http_status")
    retry_count = int(metadata.get("retry_count", 0) or 0)
    parts = [f"模型错误: {code}"]
    if status is not None:
        parts.append(f"HTTP {status}")
    if retry_count:
        parts.append(f"重试 {retry_count} 次")
    message = str(metadata.get("message", "")).strip()
    if message:
        parts.append(message)
    return "；".join(parts)
