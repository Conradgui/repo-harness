"""Turn-level runtime engine.

The runtime owns state and persistence. Engine owns the control loop that turns
one user request into model calls, tool executions, and user-visible events.
"""

import time

from ..providers.base import complete_model
from ..task_state import TaskState
from ..workspace import clip, now
from .engine_helpers import (
    execute_tool_payload,
    finish_limited_run,
    finish_stopped_run,
    maintain_memory_safely,
    request_step_limit_summary,
    should_retry_model_error,
)
from .model_errors import finish_model_error

CHECKPOINT_NONE_STATUS = "no-checkpoint"
CHECKPOINT_PARTIAL_STALE_STATUS = "partial-stale"
CHECKPOINT_WORKSPACE_MISMATCH_STATUS = "workspace-mismatch"


class Engine:
    def __init__(self, runtime):
        self.runtime = runtime

    def ask(self, user_message):
        final_answer = ""
        try:
            for event in self.run_turn(user_message):
                if event["type"] in {"final", "stop"}:
                    final_answer = event["content"]
        finally:
            # Reset the abort flag on every exit path (model error, step
            # limit, normal finish, exception), so a later turn/session does
            # not inherit a stale abort.
            agent = self.runtime
            if getattr(agent, "abort_requested", False):
                agent.abort_requested = False
        return final_answer

    def drain_worker_notifications(self):
        agent = self.runtime
        notifications = agent.worker_manager.drain_notifications()
        for notification in notifications:
            agent.record({"role": "user", "content": notification, "created_at": now()})
            agent.session_event_bus.emit(
                "worker_notification_drained",
                {
                    "run_id": getattr(agent, "current_run_id", ""),
                    "content": clip(notification, 500),
                },
            )
        return notifications

    def _drain_worker_notification_events(self):
        for notification in self.drain_worker_notifications():
            yield {
                "type": "worker_notification",
                "run_id": getattr(self.runtime, "current_run_id", ""),
                "content": notification,
            }

    def run_turn(self, user_message):
        agent = self.runtime
        run_started_at = time.monotonic()
        task_state = TaskState.create(
            run_id=agent.new_run_id(),
            task_id=agent.new_task_id(),
            user_request=user_message,
        )
        task_state.resume_status = agent.resume_state.get("status", CHECKPOINT_NONE_STATUS)
        agent.current_task_state = task_state
        agent.current_turn_id = task_state.task_id
        agent.current_run_id = task_state.run_id
        agent.current_run_dir = agent.run_store.start_run(task_state)
        agent._run_changed_paths = []
        agent.runtime_reminders = []
        # G2: per-run escalation state; each run may escalate each root once.
        agent._blocked_upgraded_roots = set()
        agent.last_ask_user_answer = ""
        agent.session_event_bus.emit(
            "turn_started",
            {
                "run_id": task_state.run_id,
                "task_id": task_state.task_id,
                "runtime_mode": agent.runtime_mode,
                "user_request": clip(user_message, 300),
            },
        )
        yield {
            "type": "turn_started",
            "run_id": task_state.run_id,
            "task_id": task_state.task_id,
        }

        agent.memory.set_task_summary(user_message)
        agent.record({"role": "user", "content": user_message, "created_at": now()})
        agent.emit_trace(
            task_state,
            "run_started",
            {
                "task_id": task_state.task_id,
                "user_request": clip(user_message, 300),
            },
        )

        tool_steps = 0
        attempts = 0
        provider_retries = {}
        max_attempts = agent.max_steps + 2

        while tool_steps < agent.max_steps and attempts < max_attempts:
            if agent.abort_requested:
                yield from finish_stopped_run(
                    self,
                    task_state,
                    user_message,
                    "Stopped after abort request.",
                    "aborted",
                    run_started_at,
                )
                return
            yield from self._drain_worker_notification_events()
            attempts += 1
            task_state.record_attempt()
            agent.run_store.write_task_state(task_state)
            prompt_started_at = time.monotonic()
            prompt, prompt_metadata = agent._build_prompt_and_metadata(user_message)
            agent.emit_trace(
                task_state,
                "prompt_built",
                {
                    "prompt_metadata": prompt_metadata,
                    "duration_ms": int((time.monotonic() - prompt_started_at) * 1000),
                },
            )
            agent.session_event_bus.emit(
                "context_usage_recorded",
                {
                    "run_id": task_state.run_id,
                    "turn_id": task_state.task_id,
                    "context_usage": prompt_metadata.get("context_usage", {}),
                },
            )
            if prompt_metadata.get("resume_status") == CHECKPOINT_PARTIAL_STALE_STATUS:
                checkpoint = agent.create_checkpoint(
                    task_state, user_message, trigger="freshness_mismatch"
                )
                agent.run_store.write_task_state(task_state)
                agent.emit_trace(
                    task_state,
                    "checkpoint_created",
                    {
                        "checkpoint_id": checkpoint["checkpoint_id"],
                        "trigger": "freshness_mismatch",
                    },
                )
            elif prompt_metadata.get("resume_status") == CHECKPOINT_WORKSPACE_MISMATCH_STATUS:
                agent.emit_trace(
                    task_state,
                    "runtime_identity_mismatch",
                    {
                        "fields": list(
                            prompt_metadata.get("runtime_identity_mismatch_fields", [])
                        ),
                    },
                )
                checkpoint = agent.create_checkpoint(
                    task_state, user_message, trigger="workspace_mismatch"
                )
                agent.run_store.write_task_state(task_state)
                agent.emit_trace(
                    task_state,
                    "checkpoint_created",
                    {
                        "checkpoint_id": checkpoint["checkpoint_id"],
                        "trigger": "workspace_mismatch",
                    },
                )
            if prompt_metadata.get("budget_reductions"):
                checkpoint = agent.create_checkpoint(
                    task_state, user_message, trigger="context_reduction"
                )
                agent.run_store.write_task_state(task_state)
                agent.emit_trace(
                    task_state,
                    "checkpoint_created",
                    {
                        "checkpoint_id": checkpoint["checkpoint_id"],
                        "trigger": "context_reduction",
                    },
                )
            agent.emit_trace(
                task_state,
                "model_requested",
                {
                    "attempts": task_state.attempts,
                    "tool_steps": task_state.tool_steps,
                    "prompt_cache_key": prompt_metadata.get("prompt_cache_key"),
                },
            )
            agent.session_event_bus.emit(
                "model_requested",
                {
                    "run_id": task_state.run_id,
                    "attempts": task_state.attempts,
                    "tool_steps": task_state.tool_steps,
                },
            )
            yield {
                "type": "model_requested",
                "run_id": task_state.run_id,
                "attempts": task_state.attempts,
                "tool_steps": task_state.tool_steps,
            }

            prompt_cache_key = None
            prompt_cache_retention = None
            if getattr(agent.model_client, "supports_prompt_cache", False):
                prompt_cache_key = prompt_metadata.get("prompt_cache_key")
                prompt_cache_retention = "in_memory"

            model_started_at = time.monotonic()
            try:
                result = complete_model(
                    agent.model_client,
                    prompt,
                    agent.max_new_tokens,
                    prompt_cache_key=prompt_cache_key,
                    prompt_cache_retention=prompt_cache_retention,
                )
            except Exception as exc:
                if agent.abort_requested:
                    yield from finish_stopped_run(
                        self,
                        task_state,
                        user_message,
                        "Stopped after abort request.",
                        "aborted",
                        run_started_at,
                    )
                    return
                if should_retry_model_error(exc, provider_retries):
                    code = getattr(exc, "code", type(exc).__name__)
                    provider_retries[code] = provider_retries.get(code, 0) + 1
                    agent.session_event_bus.emit(
                        "model_retry_scheduled",
                        {
                            "run_id": task_state.run_id,
                            "code": code,
                            "attempts": task_state.attempts,
                            "retry_count": provider_retries[code],
                        },
                    )
                    agent.emit_trace(
                        task_state,
                        "model_retry_scheduled",
                        {
                            "code": code,
                            "duration_ms": int(
                                (time.monotonic() - model_started_at) * 1000
                            ),
                            "retry_count": provider_retries[code],
                        },
                    )
                    continue
                yield from finish_model_error(
                    self,
                    task_state,
                    user_message,
                    prompt_metadata,
                    exc,
                    int((time.monotonic() - model_started_at) * 1000),
                    int((time.monotonic() - run_started_at) * 1000),
                )
                return
            if agent.abort_requested:
                yield from finish_stopped_run(
                    self,
                    task_state,
                    user_message,
                    "Stopped after abort request.",
                    "aborted",
                    run_started_at,
                )
                return
            raw = result.text
            completion_metadata = dict(
                result.metadata
                or getattr(agent.model_client, "last_completion_metadata", {})
                or {}
            )
            if completion_metadata:
                prompt_metadata.update(completion_metadata)
            agent.last_completion_metadata = completion_metadata
            agent.last_prompt_metadata = prompt_metadata
            kind, payload = agent.parse(raw)
            duration_ms = int((time.monotonic() - model_started_at) * 1000)
            agent.emit_trace(
                task_state,
                "model_parsed",
                {
                    "kind": kind,
                    "completion_metadata": completion_metadata,
                    "duration_ms": duration_ms,
                },
            )
            agent.session_event_bus.emit(
                "model_parsed",
                {"run_id": task_state.run_id, "kind": kind, "duration_ms": duration_ms},
            )
            yield {
                "type": "model_parsed",
                "run_id": task_state.run_id,
                "kind": kind,
                "duration_ms": duration_ms,
            }

            if kind in {"tool", "tools"}:
                tools = [payload] if kind == "tool" else list(payload)
                for tool_payload in tools:
                    if tool_steps >= agent.max_steps:
                        break
                    yield from execute_tool_payload(
                        self, task_state, user_message, tool_payload
                    )
                    tool_steps += 1
                    # G2: a blocked tool may need deterministic escalation. The
                    # reminder list already accumulated the failure; decide here
                    # and surface (callback when interactive, event otherwise).
                    last_status = str(getattr(agent, "_last_tool_result_metadata", {}).get("tool_status", "") or "")
                    if last_status in {"rejected", "error"}:
                        upgrade = agent.evaluate_blocked_state()
                        if upgrade is not None:
                            agent.upgrade_to_user(upgrade["question"], choices=[])
                    if agent.abort_requested:
                        break
                if agent.abort_requested:
                    yield from finish_stopped_run(
                        self,
                        task_state,
                        user_message,
                        "Stopped after abort request.",
                        "aborted",
                        run_started_at,
                    )
                    return
                continue

            if kind == "retry":
                agent.record({"role": "assistant", "content": payload, "created_at": now()})
                agent.session_event_bus.emit(
                    "assistant_message",
                    {
                        "run_id": task_state.run_id,
                        "kind": "retry",
                        "content": clip(payload, 500),
                    },
                )
                agent.run_store.write_task_state(task_state)
                yield {"type": "retry", "run_id": task_state.run_id, "content": payload}
                continue

            final = (payload or raw).strip()
            yield from self._drain_worker_notification_events()
            if agent.runtime_mode == "plan" and not agent.plan_mode.can_finish():
                notice = agent.plan_mode.final_notice()
                agent.record({"role": "assistant", "content": notice, "created_at": now()})
                agent.emit_trace(
                    task_state,
                    "runtime_notice",
                    {"content": notice, "status": "blocked"},
                )
                agent.session_event_bus.emit(
                    "assistant_message",
                    {
                        "run_id": task_state.run_id,
                        "kind": "runtime_notice",
                        "content": notice,
                    },
                )
                agent.run_store.write_task_state(task_state)
                yield {
                    "type": "runtime_notice",
                    "run_id": task_state.run_id,
                    "content": notice,
                }
                continue

            agent.record({"role": "assistant", "content": final, "created_at": now()})
            if agent.runtime_mode == "plan":
                agent.exit_plan_mode()
            agent.session_event_bus.emit(
                "assistant_message",
                {
                    "run_id": task_state.run_id,
                    "kind": "final",
                    "content": clip(final, 500),
                },
            )
            task_state.finish_success(final)
            agent.promote_durable_memory(user_message, final)
            maintain_memory_safely(agent, task_state, final)
            checkpoint = agent.create_checkpoint(task_state, user_message, trigger="run_finished")
            agent._finalize_runtime_evidence(task_state)
            agent.run_store.write_task_state(task_state)
            agent.emit_trace(
                task_state,
                "checkpoint_created",
                {"checkpoint_id": checkpoint["checkpoint_id"], "trigger": "run_finished"},
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
            agent.session_event_bus.emit(
                "turn_finished",
                {
                    "run_id": task_state.run_id,
                    "status": task_state.status,
                    "stop_reason": task_state.stop_reason,
                    "duration_ms": int((time.monotonic() - run_started_at) * 1000),
                },
            )
            agent.run_store.write_report(
                task_state, agent.redact_artifact(agent.build_report(task_state))
            )
            yield from self._drain_worker_notification_events()
            yield {"type": "final", "run_id": task_state.run_id, "content": final}
            yield {
                "type": "turn_finished",
                "run_id": task_state.run_id,
                "status": task_state.status,
                "stop_reason": task_state.stop_reason,
            }
            agent.current_turn_id = ""
            agent.current_run_id = ""
            return

        if attempts >= max_attempts and tool_steps < agent.max_steps:
            final = "Stopped after too many malformed model responses without a valid tool call or final answer."
            task_state.stop_retry_limit(final)
        else:
            summary = None
            if tool_steps > 0:
                summary = request_step_limit_summary(self, task_state, user_message)
            if summary:
                final = (
                    summary
                    + "\n\n已达本轮 step 预算上限（max_steps）。继续工作：在 REPL 输入 /resume "
                    "续接本会话，或直接说「继续」让我接着干。"
                )
            else:
                final = "Stopped after reaching the step limit without a final answer."
            task_state.stop_step_limit(final)
        yield from finish_limited_run(self, task_state, user_message, final, run_started_at)
