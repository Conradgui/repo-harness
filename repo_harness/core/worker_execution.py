"""Worker execution helpers."""

import time

from ..workspace import now


def run_worker(manager, task, prompt, action="spawn"):
    started_at = time.monotonic()
    item = manager._get_item(task.id)
    item["status"] = "running"
    item["updated_at"] = now()
    manager.runtime.session_event_bus.emit(
        "worker_started",
        {"worker_id": task.id, "action": action, "subagent_type": task.subagent_type},
    )
    manager._save()
    try:
        if task.stop_requested:
            result = "worker stopped before execution"
            status = "stopped"
        else:
            result = task.runtime.ask(str(prompt))
            status = "completed"
    except Exception as exc:
        result = f"error: worker failed: {exc}"
        status = "failed"
    manager._finish_task(task, status, result, started_at)
    manager.runtime.session_event_bus.emit(
        "worker_completed",
        {"worker_id": task.id, "status": status, "action": action},
    )
    return result


def run_worker_turn(worker):
    return worker.run()
