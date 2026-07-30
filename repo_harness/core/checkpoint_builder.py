"""Pure checkpoint-building helpers extracted from RepoHarness.

These functions assemble checkpoint data without mutating runtime state.
The runtime keeps thin forward methods that supply the state and persist
the result.
"""

from __future__ import annotations

import uuid

from ..workspace import clip, now

CHECKPOINT_SCHEMA_VERSION = "phase1-v1"


def build_checkpoint(task_state, user_message, trigger, recent_files, file_freshness_fn, parent_checkpoint_id, runtime_identity):
    """Assemble a checkpoint dict from runtime state.

    *recent_files* is a list of relative paths; *file_freshness_fn* is a
    callable ``(path) -> str`` that returns a freshness hash for a given
    file (typically ``memory.file_freshness``).
    """
    checkpoint_id = "ckpt_" + uuid.uuid4().hex[:8]
    key_files = []
    freshness = {}
    for path in recent_files:
        fp = file_freshness_fn(path)
        freshness[path] = fp
        key_files.append({"path": path, "freshness": fp})
    return {
        "checkpoint_id": checkpoint_id,
        "parent_checkpoint_id": parent_checkpoint_id,
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "created_at": now(),
        "current_goal": str(user_message),
        "completed": [task_state.final_answer] if task_state.final_answer else [],
        "excluded": [],
        "current_blocker": "" if str(task_state.stop_reason or "") in ("", "final_answer_returned") else str(task_state.stop_reason),
        "next_step": infer_next_step(task_state),
        "key_files": key_files,
        "freshness": freshness,
        "summary": f"{trigger}: {clip(str(user_message), 120)}",
        "runtime_identity": runtime_identity,
    }


def infer_next_step(task_state):
    """Produce a human-readable hint for resuming from a checkpoint."""
    if task_state.status == "completed":
        return "No next step recorded."
    if task_state.stop_reason == "step_limit_reached":
        return "Resume from the latest checkpoint and continue the task."
    if task_state.last_tool:
        return f"Decide the next action after {task_state.last_tool}."
    return "Continue the task from the latest checkpoint."
