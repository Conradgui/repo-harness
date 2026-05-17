"""Session-scoped todo ledger."""

from .workspace import now


class TodoLedger:
    def __init__(self, runtime):
        self.runtime = runtime
        self.runtime.session.setdefault("todos", {"next_id": 1, "items": []})
        self.runtime.session.setdefault("todo_changes", [])

    @property
    def state(self):
        return self.runtime.session.setdefault("todos", {"next_id": 1, "items": []})

    def add(self, text, status="pending"):
        todo_id = f"todo_{int(self.state.get('next_id', 1))}"
        self.state["next_id"] = int(self.state.get("next_id", 1)) + 1
        item = {
            "id": todo_id,
            "text": str(text).strip(),
            "status": str(status or "pending").strip(),
            "created_at": now(),
            "updated_at": now(),
        }
        if not item["text"]:
            raise ValueError("todo text must not be empty")
        self.state.setdefault("items", []).append(item)
        self._record_change("add", item)
        return dict(item)

    def update(self, todo_id, **changes):
        item = self.get(todo_id)
        for key in ("text", "status"):
            if key in changes and changes[key] is not None:
                value = str(changes[key]).strip()
                if key == "text" and not value:
                    raise ValueError("todo text must not be empty")
                item[key] = value
        item["updated_at"] = now()
        self._record_change("update", item)
        return dict(item)

    def get(self, todo_id):
        for item in self.state.setdefault("items", []):
            if item.get("id") == str(todo_id):
                return item
        raise ValueError(f"unknown todo id: {todo_id}")

    def to_dict(self):
        return {"next_id": self.state.get("next_id", 1), "items": [dict(item) for item in self.state.get("items", [])]}

    def render(self):
        items = self.state.get("items", [])
        if not items:
            return "Todos:\n- none"
        return "\n".join(["Todos:", *[f"- {item['id']} [{item['status']}] {item['text']}" for item in items]])

    def render_prompt(self):
        items = self.state.get("items", [])
        if not items:
            return ""
        return "\n".join(["Todo ledger:", *[f"- {item['id']} [{item['status']}] {item['text']}" for item in items[:12]]])

    def _record_change(self, action, item):
        payload = {"action": action, "todo": dict(item)}
        self.runtime.session.setdefault("todo_changes", []).append(payload)
        task_state = getattr(self.runtime, "current_task_state", None)
        if task_state is not None and hasattr(task_state, "todo_changes"):
            task_state.todo_changes.append(payload)
        self.runtime.session_path = self.runtime.session_store.save(self.runtime.session)
