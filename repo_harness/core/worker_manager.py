"""Session-scoped worker lifecycle for subagents.

Provides three execution modes:
- spawn(): single worker (existing)
- parallel(): multiple workers concurrently, wait for all
- pipeline(): sequential stages, output of one feeds the next
"""

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
        # 先读取当前状态决定新状态
        current = self._get_item(task_id)
        new_status = "stopped" if current.get("status") != "running" else "stopping"
        item = self._update_item(task_id, {"status": new_status})
        task = self._tasks.get(str(task_id))
        if task is not None:
            task.stop_requested = True
            abort = getattr(task.runtime, "abort_current_turn", None)
            if callable(abort):
                abort()
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

    # ------------------------------------------------------------------
    # 编排原语：parallel 和 pipeline
    # ------------------------------------------------------------------

    def parallel(self, tasks, timeout=120):
        """并行执行多个 worker，等待全部完成，返回结构化结果。

        Args:
            tasks: list of dicts, each with keys:
                - description (str): task description
                - prompt (str): prompt to send to the worker
                - subagent_type (str, optional): "Explore" or "worker"
                - write_scope (list, optional): allowed write paths
            timeout: max seconds to wait for all workers

        Returns:
            list of dicts with keys: id, status, result, duration_ms, description
        """
        started_at = time.monotonic()
        spawned = []
        for task_def in tasks:
            desc = task_def.get("description", "parallel task")
            prompt = task_def.get("prompt", "")
            subagent_type = task_def.get("subagent_type", "Explore")
            write_scope = task_def.get("write_scope")
            payload = self.spawn(desc, prompt, subagent_type=subagent_type, write_scope=write_scope)
            spawned.append(payload)

        # 等待所有 worker 完成（仅后台模式需要等待）
        if self._can_run_background():
            deadline = started_at + float(timeout)
            for payload in spawned:
                task = self._tasks.get(payload.get("id", ""))
                if task and task.thread and task.thread.is_alive():
                    remaining = max(0.1, deadline - time.monotonic())
                    task.thread.join(timeout=remaining)

        # 收集结果
        results = []
        for payload in spawned:
            worker_id = payload.get("id", "")
            item = self._get_item(worker_id)
            results.append({
                "id": worker_id,
                "status": item.get("status", "unknown"),
                "result": item.get("result", ""),
                "duration_ms": item.get("duration_ms", 0),
                "description": item.get("description", ""),
            })
        return results

    def pipeline(self, stages, initial_input="", timeout_per_stage=120):
        """串行执行多个 stage，前一个的输出作为后一个的输入。

        Args:
            stages: list of dicts, each with:
                - description: str
                - prompt_template: str with {input} placeholder (replaced with previous output)
                - subagent_type: str, optional
                - write_scope: list, optional
            initial_input: str fed to the first stage
            timeout_per_stage: max seconds per stage

        Returns:
            list of dicts with keys: id, stage_index, status, result, duration_ms, description
        """
        results = []
        current_input = str(initial_input)

        for index, stage_def in enumerate(stages):
            desc = stage_def.get("description", f"pipeline stage {index}")
            prompt_template = stage_def.get("prompt_template", "{input}")
            prompt = prompt_template.replace("{input}", current_input)
            subagent_type = stage_def.get("subagent_type", "Explore")
            write_scope = stage_def.get("write_scope")

            payload = self.spawn(desc, prompt, subagent_type=subagent_type, write_scope=write_scope)
            worker_id = payload.get("id", "")

            # 等待完成
            task = self._tasks.get(worker_id)
            if task and task.thread and task.thread.is_alive():
                task.thread.join(timeout=float(timeout_per_stage))

            item = self._get_item(worker_id)
            status = item.get("status", "unknown")
            result = item.get("result", "")

            stage_result = {
                "id": worker_id,
                "stage_index": index,
                "description": desc,
                "status": status,
                "result": result,
                "duration_ms": item.get("duration_ms", 0),
            }
            results.append(stage_result)

            # 失败传播：如果当前 stage 失败，停止后续 stage
            if status in ("failed", "stopped"):
                for remaining_index in range(index + 1, len(stages)):
                    results.append({
                        "id": "",
                        "stage_index": remaining_index,
                        "description": stages[remaining_index].get("description", f"pipeline stage {remaining_index}"),
                        "status": "skipped",
                        "result": f"skipped: stage {index} {status}",
                        "duration_ms": 0,
                    })
                break

            current_input = result

        return results

    def dag(self, tasks, timeout=180):
        """DAG 编排：支持依赖关系的并行执行。

        Args:
            tasks: list of dicts, each with:
                - id (str): unique task id
                - description (str): task description
                - prompt (str): prompt template with {deps:<id>} placeholders
                - subagent_type (str, optional): "Explore" or "worker"
                - write_scope (list, optional): allowed write paths
                - depends_on (list[str], optional): task ids this depends on
            timeout: max seconds for the entire DAG

        Returns:
            dict with keys:
                - results: list of result dicts
                - execution_order: list of task ids in execution order
                - failed: list of task ids that failed
        """
        started_at = time.monotonic()
        task_map = {t["id"]: dict(t) for t in tasks}
        completed = {}  # id -> result string
        results = []
        execution_order = []
        failed = []
        pending = set(task_map.keys())

        while pending:
            # 找到所有依赖已满足的任务
            ready = []
            for tid in pending:
                deps = task_map[tid].get("depends_on", [])
                if all(d in completed for d in deps):
                    ready.append(tid)

            if not ready:
                # 没有 ready 的任务但还有 pending → 循环依赖或不可达
                for tid in pending:
                    results.append({
                        "id": tid, "stage_index": -1,
                        "description": task_map[tid].get("description", tid),
                        "status": "blocked", "result": "unresolvable dependency",
                        "duration_ms": 0,
                    })
                    failed.append(tid)
                break

            # 并行执行所有 ready 的任务
            batch_tasks = []
            for tid in ready:
                tdef = task_map[tid]
                # 替换 prompt 中的依赖引用
                prompt = tdef.get("prompt", "")
                for dep_id in tdef.get("depends_on", []):
                    prompt = prompt.replace(f"{{deps:{dep_id}}}", completed.get(dep_id, ""))
                batch_tasks.append({
                    "description": tdef.get("description", tid),
                    "prompt": prompt,
                    "subagent_type": tdef.get("subagent_type", "Explore"),
                    "write_scope": tdef.get("write_scope"),
                })

            batch_results = self.parallel(batch_tasks, timeout=max(10, timeout - int(time.monotonic() - started_at)))

            for tid, batch_result in zip(ready, batch_results):
                execution_order.append(tid)
                results.append({
                    "id": tid, "stage_index": len(results),
                    "description": batch_result.get("description", tid),
                    "status": batch_result.get("status", "unknown"),
                    "result": batch_result.get("result", ""),
                    "duration_ms": batch_result.get("duration_ms", 0),
                })
                if batch_result.get("status") == "completed":
                    completed[tid] = batch_result.get("result", "")
                else:
                    failed.append(tid)
                pending.discard(tid)

            # 如果有失败，跳过依赖它的任务
            if failed:
                blocked = []
                for tid in list(pending):
                    deps = task_map[tid].get("depends_on", [])
                    if any(d in failed for d in deps):
                        blocked.append(tid)
                for tid in blocked:
                    execution_order.append(tid)
                    results.append({
                        "id": tid, "stage_index": len(results),
                        "description": task_map[tid].get("description", tid),
                        "status": "skipped",
                        "result": f"skipped: dependency failed ({[d for d in task_map[tid].get('depends_on', []) if d in failed]})",
                        "duration_ms": 0,
                    })
                    failed.append(tid)
                    pending.discard(tid)

        return {
            "results": results,
            "execution_order": execution_order,
            "failed": failed,
        }

    def post_message(self, channel, message):
        """向消息通道发送消息（worker 间通信）。"""
        messages = self.runtime.session.setdefault("worker_messages", {})
        messages.setdefault(channel, []).append({
            "content": str(message),
            "posted_at": now(),
        })
        self._save()

    def read_messages(self, channel, since=0):
        """读取消息通道中的消息。since=0 表示读取全部。"""
        messages = self.runtime.session.get("worker_messages", {}).get(channel, [])
        return messages[since:]

    def clear_messages(self, channel=None):
        """清空消息通道。"""
        if channel:
            self.runtime.session.get("worker_messages", {}).pop(channel, None)
        else:
            self.runtime.session["worker_messages"] = {}
        self._save()

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
        with self._lock:
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
        self._update_item(task.id, {"status": "running"})
        self._save()
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
        """返回 item 的副本（只读用途）。"""
        with self._lock:
            for item in self.state.setdefault("items", []):
                if item.get("id") == str(task_id):
                    return dict(item)
        raise ValueError(f"unknown worker: {task_id}")

    def _update_item(self, task_id, updates):
        """原子更新 item 字段（持锁修改）。"""
        with self._lock:
            for item in self.state.setdefault("items", []):
                if item.get("id") == str(task_id):
                    item.update(updates)
                    item["updated_at"] = now()
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
        artifacts = collect_worker_artifacts(task.runtime)
        item = self._update_item(task.id, {
            "status": status,
            "result": str(result),
            "duration_ms": int((time.monotonic() - started_at) * 1000),
            **artifacts,
        })
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
