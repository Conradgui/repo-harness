"""Plan mode artifact and runtime state helpers."""

import re

from .workspace import now


def slugify(value):
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip().lower()).strip("-._")
    return slug or "plan"


class PlanModeManager:
    def __init__(self, runtime):
        self.runtime = runtime

    @property
    def state(self):
        return self.runtime.session.setdefault(
            "runtime_mode",
            {"mode": "default", "active_plan_path": "", "topic": ""},
        )

    def enter(self, topic):
        if self.state.get("mode") == "plan":
            return str(self.state.get("active_plan_path", ""))
        slug = slugify(topic)
        relative = f".repo-harness/plans/{slug}-plan.md"
        path = self.runtime.path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.state.update(
            {
                "mode": "plan",
                "topic": str(topic or slug),
                "active_plan_path": relative,
                "entered_at": now(),
            }
        )
        self.runtime.tool_profile = "plan"
        self.runtime.session_path = self.runtime.session_store.save(self.runtime.session)
        self.runtime.emit_session_event("runtime_mode_changed", mode="plan", plan_path=relative)
        return relative

    def exit(self):
        self.state.update({"mode": "default", "active_plan_path": "", "topic": "", "exited_at": now()})
        self.runtime.tool_profile = "default"
        self.runtime.session_path = self.runtime.session_store.save(self.runtime.session)
        self.runtime.emit_session_event("runtime_mode_changed", mode="default")
        return "default"

    def artifact_has_content(self):
        relative = str(self.state.get("active_plan_path", "")).strip()
        if not relative:
            return False
        path = self.runtime.path(relative)
        try:
            return path.is_file() and bool(path.read_text(encoding="utf-8").strip())
        except OSError:
            return False

    def final_block_message(self):
        relative = str(self.state.get("active_plan_path", "")).strip()
        return f"Plan mode requires a non-empty plan artifact before final answer: {relative}"

    def active_path(self):
        return str(self.state.get("active_plan_path", "")).strip()
