"""Helper routines for Engine control-loop side effects."""

import time

from ..providers.base import complete_model
from ..providers.errors import ProviderError
from ..task_state import STATUS_FAILED, STOP_REASON_PERSISTENCE_ERROR
from ..workspace import clip, now
from .context_usage import AUTO_COMPACT_THRESHOLD


def auto_compact_due(agent, usage, prompt_metadata=None):
    """auto-compact 触发判定（finding: auto-compact-unwired）。

    输入 token 占用越过 auto_compact_threshold，或本轮 prompt 已触发预算
    削减（削减本身就证明上下文压力）时，先压缩历史再重建 prompt。历史
    太短（compact_history 只保留最近 6 条）时压缩无事可做，交给削减兜底，
    这也避免了连续触发的死循环。
    """
    if len(agent.session.get("history", [])) <= 8:
        return False
    if isinstance(prompt_metadata, dict) and prompt_metadata.get("budget_reductions"):
        return True
    if isinstance(prompt_metadata, dict):
        # 真实运行的压力信号：history 的 raw 需求超过其 section 预算。
        # 下面的 rendered token 比率在真实预算计算下不可达——section 预算
        # 先把 history 裁掉，token 估算用的是裁剪后文本，占用恒低于阈值
        # （e2e 复现：注入 usage 的单测绿，真实 CLI 永不触发）。预算正在
        # 静默裁掉历史的位置，就是应该压缩历史的位置。
        history_meta = prompt_metadata.get("history") or {}
        history_budget = (prompt_metadata.get("section_budgets") or {}).get("history")
        if (
            history_budget
            and int(history_meta.get("raw_chars", 0) or 0) > int(history_budget)
        ):
            return True
    if not isinstance(usage, dict):
        return False
    window = int(usage.get("context_window", 0) or 0)
    total = int(usage.get("total_estimated_tokens", 0) or 0)
    threshold = float(usage.get("auto_compact_threshold", 0) or 0) or AUTO_COMPACT_THRESHOLD
    if window <= 0 or threshold <= 0:
        return False
    return total / window >= threshold


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


def finish_finalization_error(engine, task_state, user_message, final, exc, run_started_at):
    """final 收尾链异常的受控兜底。

    final answer 已产出但持久化环节（memory promote / checkpoint /
    task_state / report）失败时，run 不能悬在 running 或宣称 completed：
    降级为 failed + persistence_error，并把 task_state 与 report 以失败
    终态落盘——这是崩溃恢复能依赖的最小保证。
    """
    agent = engine.runtime
    notice = (
        "The final answer was produced, but persisting run artifacts failed. "
        "The run is recorded as failed rather than left in a running state: "
        + clip(str(exc), 300)
    )
    task_state.stop(
        STOP_REASON_PERSISTENCE_ERROR,
        status=STATUS_FAILED,
        final_answer=final,
    )
    agent.record({"role": "assistant", "content": notice, "created_at": now()})
    agent.session_event_bus.emit(
        "assistant_message",
        {"run_id": task_state.run_id, "kind": "finalization_error", "content": clip(notice, 500)},
    )
    agent.emit_trace(
        task_state,
        "finalization_error",
        {"error": clip(str(exc), 300), "status": task_state.status},
    )
    # 最小落盘保证：task_state 先行（即使后续步骤再失败，run 也不悬在
    # running）；report 随后。这两个 write 自身失败则异常继续传播——
    # 崩溃安全兜底自身崩溃时已无计可施。
    agent.run_store.write_task_state(task_state)
    agent.session_event_bus.emit(
        "turn_finished",
        {
            "run_id": task_state.run_id,
            "status": task_state.status,
            "stop_reason": task_state.stop_reason,
            "duration_ms": int((time.monotonic() - run_started_at) * 1000),
        },
    )
    # report 不走 build_report：它内部依赖 evidence / memory_outcome /
    # worker_manager 等子系统，其中任何一个都可能是刚才炸掉的那个。
    # 兜底 report 独立构造，只依赖已稳定的 task_state。
    agent.run_store.write_report(
        task_state, agent.redact_artifact(_minimal_failure_report(task_state))
    )
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
    agent.current_turn_id = ""
    agent.current_run_id = ""
    yield {"type": "stop", "run_id": task_state.run_id, "content": notice}
    yield {
        "type": "turn_finished",
        "run_id": task_state.run_id,
        "status": task_state.status,
        "stop_reason": task_state.stop_reason,
    }


def _minimal_failure_report(task_state):
    """兜底用的最小 report：字段与 build_report 的核心列对齐，
    但不依赖任何可能在故障中的 runtime 子系统。"""
    return {
        "run_id": task_state.run_id,
        "task_id": task_state.task_id,
        "status": task_state.status,
        "stop_reason": task_state.stop_reason,
        "final_answer": task_state.final_answer,
        "tool_steps": task_state.tool_steps,
        "attempts": task_state.attempts,
        "task_state": task_state.to_dict(),
    }


def should_retry_model_error(exc, provider_retries):
    if not isinstance(exc, ProviderError):
        return False
    code = str(getattr(exc, "code", "") or "")
    # empty_response 保留在重试集合里：旧注入路径构造的 ProviderError
    # 可能没显式设置 retryable，行为与归一化之前保持一致。
    retryable = bool(getattr(exc, "retryable", False)) or code == "empty_response"
    if not retryable:
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
