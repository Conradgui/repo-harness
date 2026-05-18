"""Session-scoped worker lifecycle for subagents."""

import queue
import threading
import time
from dataclasses import dataclass, field

from ..workspace import now
from .worker_artifacts import collect_worker_artifacts
from .worker_execution import run_worker
from .worker_runtime import build_child_runtime


@dataclass
class WorkerTask:
    id: str
    description: str
    subagent_type: str
    write_scope: tuple[str, ...]
    runtime: object
    thread: threading.Thread | None = None
    stop_requested: bool = False
    state: dict = field(default_factory=dict)


class WorkerManager:
    def __init__(self, runtime):
        self.runtime = runtime
        self.runtime.session.setdefault("workers", {"next_id": 1, "items": []})
        self._tasks = {}
        self._lock = threading.Lock()
        self._notifications = queue.Queue()

    @property
    def state(self):
        return self.runtime.session.setdefault("workers", {"next_id": 1, "items": []})

    def spawn(self, description, prompt, subagent_type="worker", write_scope=None):
        subagent_type = _clean_type(subagent_type)
        if self.runtime.runtime_mode == "plan" and subagent_type != "Explore":
            raise ValueError("plan mode only allows Explore workers")
        task = self._new_task(description, subagent_type, write_scope)
        self._tasks[task.id] = task
        if self._can_run_background():
            self._start_background(task, prompt, action="spawn")
            return self._public_payload(task, status="started")
        run_worker(self, task, prompt, action="spawn")
        payload = self._payload_with_result(task)
        if subagent_type == "worker" and payload.get("status") == "completed":
            payload["status"] = "running"
        return payload

    def send(self, worker_id, message):
        return self.continue_task(worker_id, message)

    def continue_task(self, task_id, message):
        task = self._get_active_task(task_id)
        item = self._get_item(task_id)
        if item.get("status") in {"running", "stopping"} and self._can_run_background():
            raise ValueError(f"worker is running: {task_id}")
        if self.runtime.runtime_mode == "plan" and task.subagent_type != "Explore":
            raise ValueError("plan mode only allows Explore workers")
        if self._can_run_background():
            self._start_background(task, message, action="continue")
            return self._public_payload(task, status="started")
        run_worker(self, task, message, action="continue")
        return self._payload_with_result(task)

    def stop(self, worker_id):
        return self.stop_task(worker_id)

    def stop_task(self, task_id):
        item = self._get_item(task_id)
        task = self._tasks.get(str(task_id))
        if task is not None:
            task.stop_requested = True
            abort = getattr(task.runtime, "abort_current_turn", None)
            if callable(abort):
                abort()
        with self._lock:
            item["status"] = "stopped" if item.get("status") != "running" else "stopping"
            item["updated_at"] = now()
        self.runtime.session_event_bus.emit(
            "worker_stop_requested",
            {"worker_id": item["id"], "status": item["status"]},
        )
        self._notifications.put((item["id"], f"{item['id']} {item['status']}"))
        self._save()
        return self._payload_with_result_id(item["id"])

    def shutdown(self, timeout=2.0):
        stopped = 0
        for task in list(self._tasks.values()):
            item = self._get_item(task.id)
            if item.get("status") in {"running", "started", "stopping"}:
                task.stop_requested = True
                stopped += 1
        deadline = time.monotonic() + float(timeout)
        for task in list(self._tasks.values()):
            thread = task.thread
            if thread is None or not thread.is_alive():
                continue
            remaining = max(0.0, deadline - time.monotonic())
            if remaining:
                thread.join(remaining)
        self._save()
        return {"stopped": stopped}

    def drain_notifications(self):
        drained = []
        while True:
            try:
                task_id, notification = self._notifications.get_nowait()
            except queue.Empty:
                break
            item = self._get_item(task_id)
            with self._lock:
                if item.get("notification_drained"):
                    continue
                item["notification_drained"] = True
                item["updated_at"] = now()
            drained.append(notification)
        if drained:
            self._save()
        return drained

    def to_dict(self):
        return {
            "next_id": int(self.state.get("next_id", 1)),
            "items": [dict(item) for item in self.state.get("items", [])],
        }

    def _new_task(self, description, subagent_type, write_scope):
        with self._lock:
            worker_id = f"agent_{int(self.state.get('next_id', 1))}"
            self.state["next_id"] = int(self.state.get("next_id", 1)) + 1
        scope = tuple(_clean_scope(write_scope))
        child = build_child_runtime(self.runtime, subagent_type, scope)
        item = {
            "id": worker_id,
            "description": str(description or "").strip() or "Worker task",
            "subagent_type": subagent_type,
            "write_scope": list(scope),
            "status": "idle",
            "result": "",
            "tool_steps": 0,
            "attempts": 0,
            "duration_ms": 0,
            "notification_drained": False,
            "created_at": now(),
            "updated_at": now(),
        }
        with self._lock:
            self.state.setdefault("items", []).append(item)
            self._save()
        return WorkerTask(worker_id, item["description"], subagent_type, scope, child)

    def _can_run_background(self):
        return getattr(self.runtime, "model_client_factory", None) is not None

    def _start_background(self, task, prompt, action):
        thread = threading.Thread(
            target=run_worker,
            args=(self, task, prompt, action),
            daemon=True,
            name=f"repo-harness-worker-{task.id}",
        )
        task.thread = thread
        thread.start()

    def _get_active_task(self, task_id):
        task = self._tasks.get(str(task_id))
        if task is None:
            raise ValueError(f"unknown or inactive worker: {task_id}")
        return task

    def _get_item(self, task_id):
        for item in self.state.setdefault("items", []):
            if item.get("id") == str(task_id):
                return item
        raise ValueError(f"unknown worker: {task_id}")

    def _public_payload(self, task, status=None):
        item = self._get_item(task.id)
        return {"id": task.id, "task_id": task.id, "status": status or item["status"], "description": task.description}

    def _payload_with_result(self, task):
        return self._payload_with_result_id(task.id)

    def _payload_with_result_id(self, task_id):
        item = self._get_item(task_id)
        payload = dict(item)
        payload["task_id"] = payload["id"]
        return payload

    def _save(self):
        self.runtime.session_path = self.runtime.session_store.save(self.runtime.session)

    def _finish_task(self, task, status, result, started_at):
        item = self._get_item(task.id)
        with self._lock:
            item["status"] = status
            item["result"] = str(result)
            item["duration_ms"] = int((time.monotonic() - started_at) * 1000)
            item["updated_at"] = now()
            item.update(collect_worker_artifacts(task.runtime))
        notification = f"{task.id} {status}: {item['result']}"
        self._notifications.put((task.id, notification))
        self.runtime.session_event_bus.emit(
            "worker_notification",
            {"worker_id": task.id, "status": status, "result": str(result)[:500]},
        )
        self._save()


def _clean_type(value):
    subagent_type = str(value or "worker").strip()
    if subagent_type.lower() == "explore":
        return "Explore"
    if subagent_type not in {"worker", "Explore"}:
        raise ValueError("subagent_type must be worker or Explore")
    return subagent_type


def _clean_scope(value):
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        raise ValueError("write_scope must be a list of workspace paths")
    return [str(item).strip() for item in value if str(item).strip()]
