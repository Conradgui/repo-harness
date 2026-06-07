"""Worker execution helpers."""

import time

from ..workspace import now

# worker 默认最大步数，防止无限循环
DEFAULT_WORKER_MAX_STEPS = 30


def run_worker(manager, task, prompt, action="spawn"):
    started_at = time.monotonic()
    manager._update_item(task.id, {"status": "running"})
    manager.runtime.session_event_bus.emit(
        "worker_started",
        {"worker_id": task.id, "action": action, "subagent_type": task.subagent_type},
    )
    manager._save()
    # 限制 worker 最大步数，防止僵尸线程
    if task.runtime.max_steps > DEFAULT_WORKER_MAX_STEPS:
        task.runtime.max_steps = DEFAULT_WORKER_MAX_STEPS
    try:
        if task.stop_requested:
            result = "worker stopped before execution"
            status = "stopped"
        else:
            result = task.runtime.ask(str(prompt))
            # 检查 task_state 是否标记为失败（模型错误时 ask() 返回错误字符串而非抛异常）
            task_state = getattr(task.runtime, "current_task_state", None)
            if task_state and getattr(task_state, "status", "") == "failed":
                status = "failed"
            else:
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
