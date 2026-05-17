"""Bounded synchronous worker manager for RepoHarness."""

from dataclasses import dataclass
from queue import Queue

from .workspace import now


@dataclass
class WorkerTask:
    id: str
    description: str
    subagent_type: str
    write_scope: list
    runtime: object


class WorkerManager:
    def __init__(self, runtime):
        self.runtime = runtime
        self.runtime.session.setdefault("workers", {"next_id": 1, "items": []})
        self._active = {}
        self._notifications = Queue()

    @property
    def state(self):
        return self.runtime.session.setdefault("workers", {"next_id": 1, "items": []})

    def spawn(self, description, prompt, subagent_type="worker", write_scope=None):
        from .runtime import RepoHarness

        subagent_type = "Explore" if str(subagent_type).lower() == "explore" else "worker"
        if getattr(self.runtime, "runtime_mode", "default") == "plan" and subagent_type != "Explore":
            raise ValueError("plan mode only allows Explore workers")
        worker_id = f"agent_{int(self.state.get('next_id', 1))}"
        self.state["next_id"] = int(self.state.get("next_id", 1)) + 1
        write_scope = [str(item).strip() for item in (write_scope or []) if str(item).strip()]
        read_only = subagent_type == "Explore"
        if subagent_type == "worker" and not write_scope:
            raise ValueError("worker write_scope must not be empty")
        child = RepoHarness(
            model_client=self.runtime.model_client,
            workspace=self.runtime.workspace,
            session_store=self.runtime.session_store,
            run_store=self.runtime.run_store,
            approval_policy="auto",
            max_steps=min(self.runtime.max_steps, 8),
            max_new_tokens=self.runtime.max_new_tokens,
            depth=self.runtime.depth + 1,
            max_depth=max(self.runtime.max_depth, self.runtime.depth + 2),
            read_only=read_only,
            secret_env_names=self.runtime.secret_env_names,
            shell_env_allowlist=self.runtime.shell_env_allowlist,
            sandbox_config=self.runtime.sandbox_config,
            write_scope=write_scope,
        )
        task = WorkerTask(worker_id, str(description), subagent_type, write_scope, child)
        self._active[worker_id] = task
        item = {
            "id": worker_id,
            "description": str(description),
            "subagent_type": subagent_type,
            "write_scope": list(write_scope),
            "status": "running",
            "created_at": now(),
            "result": "",
        }
        self.state.setdefault("items", []).append(item)
        returned = dict(item)
        try:
            result = child.ask(str(prompt))
            item["status"] = "completed" if subagent_type == "Explore" else "running"
            item["result"] = result
            returned["result"] = result
        except Exception as exc:
            result = f"error: worker failed: {exc}"
            item["status"] = "failed"
            item["result"] = result
            returned["status"] = "failed"
            returned["result"] = result
        item["updated_at"] = now()
        self.runtime.session_path = self.runtime.session_store.save(self.runtime.session)
        notification = f"{worker_id} {item['status']}: {item['result']}"
        self._notifications.put(notification)
        return returned if subagent_type == "worker" and item["status"] == "running" else dict(item)

    def send(self, worker_id, message):
        task = self._active.get(str(worker_id))
        if task is None:
            raise ValueError(f"unknown worker: {worker_id}")
        result = task.runtime.ask(str(message))
        for item in self.state.get("items", []):
            if item.get("id") == str(worker_id):
                item["status"] = "completed"
                item["result"] = result
                item["updated_at"] = now()
                self.runtime.session_path = self.runtime.session_store.save(self.runtime.session)
                self._notifications.put(f"{worker_id} completed: {result}")
                return dict(item)
        raise ValueError(f"unknown worker: {worker_id}")

    def stop(self, worker_id):
        for item in self.state.get("items", []):
            if item.get("id") == str(worker_id):
                item["status"] = "stopped"
                item["updated_at"] = now()
                self.runtime.session_path = self.runtime.session_store.save(self.runtime.session)
                self._notifications.put(f"{worker_id} stopped")
                return dict(item)
        raise ValueError(f"unknown worker: {worker_id}")

    def drain_notifications(self):
        notifications = []
        while not self._notifications.empty():
            notifications.append(self._notifications.get())
        return notifications

    def to_dict(self):
        return {"next_id": self.state.get("next_id", 1), "items": [dict(item) for item in self.state.get("items", [])]}
