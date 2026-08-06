"""Agent 运行时核心逻辑。

RepoHarness 就是包在模型外面的控制循环：负责组 prompt、解析模型输出、
校验并执行工具、写 trace、更新工作记忆，以及在合适的时候停下来。
"""

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from . import memory as memorylib
from . import runtime_evidence
from . import skills as skillslib
from . import tools as toolkit
from .context_manager import ContextManager
from .core import tool_executor as core_tool_executor
from .core.checkpoint_builder import (
    CHECKPOINT_SCHEMA_VERSION,
    build_checkpoint,
    infer_next_step,
)
from .core.engine import Engine
from .core.memory_coordinator import MemoryCoordinator
from .core.memory_outcome import MemoryOutcome
from .core.prompt_builder import (
    build_prompt_text,
    compute_tool_signature,
    filter_available_tools,
)
from .core.secret_sanitizer import SecretSanitizer
from .core.session_events import SessionEventBus
from .core.tool_profiles import build_tool_profiles
from .features import skills_runtime
from .permissions import PermissionChecker
from .plan_mode import PlanModeManager
from .run_store import RunStore
from .sandbox import SandboxConfig, SandboxRunner
from .todo_ledger import TodoLedger
from .tool_policy import ToolPolicy
from .worker_manager import WorkerManager
from .workspace import (
    IGNORED_PATH_NAMES,
    MAX_HISTORY,
    WorkspaceContext,
    clip,
    id_timestamp,
    now,
)

DEFAULT_SHELL_ENV_ALLOWLIST = ("HOME", "LANG", "LC_ALL", "LC_CTYPE", "LOGNAME", "PATH", "PWD", "SHELL", "TERM", "TMPDIR", "TMP", "TEMP", "USER")
DEFAULT_FEATURE_FLAGS = {
    "memory": True,
    "relevant_memory": True,
    "context_reduction": True,
    "prompt_cache": True,
}
CHECKPOINT_NONE_STATUS = "no-checkpoint"
CHECKPOINT_FULL_VALID_STATUS = "full-valid"
CHECKPOINT_PARTIAL_STALE_STATUS = "partial-stale"
CHECKPOINT_WORKSPACE_MISMATCH_STATUS = "workspace-mismatch"
CHECKPOINT_SCHEMA_MISMATCH_STATUS = "schema-mismatch"


@dataclass
class PromptPrefix:
    # prefix 除了文本本身，还带一小份元数据，
    # 这样 runtime 才能明确判断 prefix 是否可以复用。
    text: str
    hash: str
    workspace_fingerprint: str
    tool_signature: str
    built_at: str


class RepoHarness:
    def __init__(
        self,
        model_client,
        workspace,
        session_store,
        session=None,
        run_store=None,
        approval_policy="ask",
        max_steps=50,
        max_new_tokens=8192,
        depth=0,
        max_depth=1,
        read_only=False,
        shell_env_allowlist=None,
        secret_env_names=None,
        feature_flags=None,
        sandbox_config=None,
        write_scope=None,
        ask_user_callback=None,
        model_client_factory=None,
        parent_run_id="",
        parent_span_id="",
    ):
        self.parent_run_id = str(parent_run_id or "")
        self.parent_span_id = str(parent_span_id or "")
        self.model_client = model_client
        self.model_client_factory = model_client_factory
        self.workspace = workspace
        self.root = Path(workspace.repo_root)
        self.session_store = session_store
        self.approval_policy = approval_policy
        self.max_steps = max_steps
        self.max_new_tokens = max_new_tokens
        self.depth = depth
        self.max_depth = max_depth
        self.read_only = read_only
        self.write_scope = tuple(str(path).strip() for path in (write_scope or ()) if str(path).strip())
        self.ask_user_callback = ask_user_callback
        self.shell_env_allowlist = tuple(shell_env_allowlist or DEFAULT_SHELL_ENV_ALLOWLIST)
        self.secret_env_names = {str(name).upper() for name in (secret_env_names or ())}
        self._secret_sanitizer = SecretSanitizer(
            self.secret_env_names, self.shell_env_allowlist, self.root
        )
        self.feature_flags = dict(DEFAULT_FEATURE_FLAGS)
        if feature_flags:
            self.feature_flags.update({str(key): bool(value) for key, value in feature_flags.items()})
        self.run_store = run_store or RunStore(Path(workspace.repo_root) / ".repo-harness" / "runs")
        self.sandbox_config = sandbox_config or SandboxConfig()
        self.sandbox_runner = SandboxRunner(self.sandbox_config)
        self.session = session or {
            "id": id_timestamp() + "-" + uuid.uuid4().hex[:6],
            "created_at": now(),
            "workspace_root": workspace.repo_root,
            "history": [],
            "memory": memorylib.default_memory_state(),
        }
        self._ensure_session_shape()
        self.session_event_bus = SessionEventBus(
            self.session["id"],
            self.session_store.root / f"{self.session['id']}.events.jsonl",
            redact=self.redact_artifact,
        )
        self.tool_profile = str(self.session.get("runtime_mode", {}).get("mode", "default") or "default")
        self.memory = memorylib.LayeredMemory(
            self.session.setdefault("memory", memorylib.default_memory_state()),
            workspace_root=self.root,
        )
        self.session["memory"] = self.memory.to_dict()
        # 协作者必须在 evaluate_resume_state() 之前就位——后者会调 invalidate_stale_memory。
        self.current_task_state = None
        self.memory_outcome = MemoryOutcome()
        self.memory_coordinator = MemoryCoordinator(
            self.memory,
            self.memory_outcome,
            persist=self._persist_memory,
            sync=lambda: self.session.__setitem__("memory", self.memory.to_dict()),
            source_context=lambda origin: {
                "session_id": self.session.get("id", ""),
                "run_id": self.current_task_state.run_id if self.current_task_state else "",
                "task_id": self.current_task_state.task_id if self.current_task_state else "",
                "origin": origin,
            },
        )
        self.todo_ledger = TodoLedger(self)
        self.worker_manager = WorkerManager(self)
        self.skills = skillslib.discover_skills(self.root, user_home=self._safe_user_home())
        self.tools = self.build_tools()
        self.tool_profiles = build_tool_profiles(self.tools)
        self.active_tool_profile = self.tool_profiles.get(self.tool_profile) or self.tool_profiles["default"]
        self.tool_policy = ToolPolicy(self)
        self.permission_checker = PermissionChecker(self)
        self.plan_mode = PlanModeManager(self)
        self.engine = Engine(self)
        self.prefix_state = self.build_prefix()
        self.prefix = self.prefix_state.text
        # 根据模型和 provider 动态计算 context budget
        from .context_manager import compute_budgets, detect_context_window
        _provider_name = self._infer_provider_name(model_client)
        _ctx_window = detect_context_window(
            str(getattr(model_client, "model", "")),
            _provider_name,
        )
        _total_budget, _section_budgets, _section_floors, _recent_window = compute_budgets(
            _ctx_window, max_new_tokens
        )
        self.context_window = _ctx_window
        self.context_manager = ContextManager(
            self,
            total_budget=_total_budget,
            section_budgets=_section_budgets,
            section_floors=_section_floors,
            recent_window=_recent_window,
        )
        self.resume_state = self.evaluate_resume_state()
        self.session_path = self.session_store.save(self.session)
        self.current_run_id = ""
        self.current_turn_id = ""
        self._trusted_tools = set()
        self._display = None
        self.current_run_dir = None
        self.abort_requested = False
        self.last_prompt_metadata = {}
        self.last_completion_metadata = {}
        self._last_tool_result_metadata = {}
        self._run_changed_paths = []
        self.runtime_reminders = []
        self._last_prefix_refresh = {
            "workspace_changed": False,
            "prefix_changed": False,
        }
        # Trace span state: sequential per-run ids with parent links, so a
        # run's events form a chain and child runs can name the parent span.
        self._trace_seq = 0
        self._last_trace_span_id = {}

    @classmethod
    def from_session(cls, model_client, workspace, session_store, session_id, **kwargs):
        return cls(
            model_client=model_client,
            workspace=workspace,
            session_store=session_store,
            session=session_store.load(session_id),
            **kwargs,
        )

    def _ensure_session_shape(self):
        self.session.setdefault("history", [])
        self.session.setdefault("memory", memorylib.default_memory_state())
        runtime_mode = self.session.setdefault("runtime_mode", {})
        if not isinstance(runtime_mode, dict):
            runtime_mode = {}
            self.session["runtime_mode"] = runtime_mode
        runtime_mode.setdefault("mode", "default")
        runtime_mode.setdefault("active_plan_path", "")
        runtime_mode.setdefault("topic", "")
        self.session.setdefault("compactions", [])
        checkpoints = self.session.setdefault("checkpoints", {})
        if not isinstance(checkpoints, dict):
            checkpoints = {}
            self.session["checkpoints"] = checkpoints
        checkpoints.setdefault("current_id", "")
        checkpoints.setdefault("items", {})
        runtime_identity = self.session.setdefault("runtime_identity", {})
        if not isinstance(runtime_identity, dict):
            self.session["runtime_identity"] = {}
        resume_state = self.session.setdefault("resume_state", {})
        if not isinstance(resume_state, dict):
            self.session["resume_state"] = {}

    @property
    def runtime_mode(self):
        return str(self.session.setdefault("runtime_mode", {}).get("mode", "default") or "default")

    @property
    def active_plan_path(self):
        return str(self.session.setdefault("runtime_mode", {}).get("active_plan_path", "") or "")

    def emit_session_event(self, event, **payload):
        bus = getattr(self, "session_event_bus", None)
        if bus is None:
            return {}
        return bus.emit(event, self.redact_artifact(payload))

    def enter_plan_mode(self, topic):
        return self.plan_mode.enter(topic)

    def exit_plan_mode(self):
        return self.plan_mode.exit()

    def set_tool_profile(self, name):
        name = str(name or "default")
        self.active_tool_profile = self.tool_profiles.get(name) or self.tool_profiles["default"]
        self.tool_profile = self.active_tool_profile.name
        if hasattr(self, "prefix_state"):
            self.refresh_prefix(force=True)
        return self.active_tool_profile

    def available_tools(self):
        return filter_available_tools(self.tools, getattr(self, "active_tool_profile", None))

    def current_runtime_identity(self):
        return {
            "session_id": self.session.get("id", ""),
            "cwd": str(self.root),
            "model": str(getattr(self.model_client, "model", "")),
            "model_client": self.model_client.__class__.__name__,
            "approval_policy": self.approval_policy,
            "read_only": bool(self.read_only),
            "max_steps": int(self.max_steps),
            "max_new_tokens": int(self.max_new_tokens),
            "feature_flags": dict(self.feature_flags),
            "shell_env_allowlist": list(self.shell_env_allowlist),
            "workspace_fingerprint": getattr(getattr(self, "prefix_state", None), "workspace_fingerprint", self.workspace.fingerprint()),
            "tool_signature": self.tool_signature(),
        }

    def checkpoint_state(self):
        self._ensure_session_shape()
        return self.session["checkpoints"]

    def current_checkpoint(self):
        state = self.checkpoint_state()
        checkpoint_id = str(state.get("current_id", "")).strip()
        if not checkpoint_id:
            return None
        return state.get("items", {}).get(checkpoint_id)

    def remember_candidate(self, text):
        return self.memory_coordinator.remember_candidate(text)
    def invalidate_stale_memory(self):
        return self.memory_coordinator.invalidate_stale_memory()

    def evaluate_resume_state(self):
        previous_resume_state = dict(self.session.get("resume_state", {}) or {})
        invalidated = self.invalidate_stale_memory()
        checkpoint = self.current_checkpoint()
        status = CHECKPOINT_NONE_STATUS
        stale_paths = list(invalidated)
        mismatch_fields = []
        if checkpoint:
            if checkpoint.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
                status = CHECKPOINT_SCHEMA_MISMATCH_STATUS
            else:
                for item in checkpoint.get("key_files", []):
                    path = str(item.get("path", "")).strip()
                    if not path:
                        continue
                    expected = item.get("freshness")
                    current = memorylib.file_freshness(path, self.root)
                    if expected != current and path not in stale_paths:
                        stale_paths.append(path)
                saved_identity = dict(checkpoint.get("runtime_identity", {}) or self.session.get("runtime_identity", {}) or {})
                current_identity = self.current_runtime_identity()
                identity_keys = (
                    "cwd",
                    "model",
                    "model_client",
                    "approval_policy",
                    "read_only",
                    "max_steps",
                    "max_new_tokens",
                    "feature_flags",
                    "shell_env_allowlist",
                    "workspace_fingerprint",
                    "tool_signature",
                )
                for key in identity_keys:
                    if key not in saved_identity:
                        continue
                    if saved_identity.get(key) != current_identity.get(key):
                        mismatch_fields.append(key)
                mismatch_fields.sort()
                if stale_paths:
                    status = CHECKPOINT_PARTIAL_STALE_STATUS
                elif mismatch_fields:
                    status = CHECKPOINT_WORKSPACE_MISMATCH_STATUS
                else:
                    status = CHECKPOINT_FULL_VALID_STATUS

        resume_state = {
            "status": status,
            "stale_paths": stale_paths,
            "runtime_identity_mismatch_fields": mismatch_fields,
            "stale_summary_invalidations": max(
                len(invalidated),
                int(previous_resume_state.get("stale_summary_invalidations", 0))
                if status == CHECKPOINT_PARTIAL_STALE_STATUS
                else 0,
            ),
        }
        self.session["resume_state"] = resume_state
        self.session["runtime_identity"] = self.current_runtime_identity()
        return resume_state

    def render_checkpoint_text(self):
        checkpoint = self.current_checkpoint()
        if not checkpoint:
            return ""
        lines = [
            "Task checkpoint:",
            f"- Resume status: {self.resume_state.get('status', CHECKPOINT_NONE_STATUS)}",
            f"- Current goal: {checkpoint.get('current_goal', '-') or '-'}",
            f"- Current blocker: {checkpoint.get('current_blocker', '-') or '-'}",
            f"- Next step: {checkpoint.get('next_step', '-') or '-'}",
        ]
        key_files = [str(item.get("path", "")).strip() for item in checkpoint.get("key_files", []) if str(item.get("path", "")).strip()]
        lines.append(f"- Key files: {', '.join(key_files) or '-'}")
        if checkpoint.get("completed"):
            lines.append("- Completed: " + " | ".join(str(item) for item in checkpoint.get("completed", [])))
        if checkpoint.get("excluded"):
            lines.append("- Excluded: " + " | ".join(str(item) for item in checkpoint.get("excluded", [])))
        if self.resume_state.get("stale_paths"):
            lines.append("- Stale paths: " + ", ".join(self.resume_state["stale_paths"]))
        summary = str(checkpoint.get("summary", "")).strip()
        if summary:
            lines.append(f"- Summary: {summary}")
        return "\n".join(lines)

    @staticmethod
    def remember(bucket, item, limit):
        if not item:
            return
        if item in bucket:
            bucket.remove(item)
        bucket.append(item)
        del bucket[:-limit]

    def build_tools(self):
        return toolkit.build_tool_registry(self)

    def tool_signature(self):
        return compute_tool_signature(self.tools)

    def build_prefix(self):
        text = build_prompt_text(self.available_tools(), self.skills)
        text = text + "\n\n" + self.workspace.text()
        return PromptPrefix(
            text=text,
            hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            workspace_fingerprint=self.workspace.fingerprint(),
            tool_signature=self.tool_signature(),
            built_at=now(),
        )

    def _apply_prefix_state(self, prefix_state):
        self.prefix_state = prefix_state
        self.prefix = prefix_state.text

    def refresh_prefix(self, force=False):
        previous_hash = getattr(getattr(self, "prefix_state", None), "hash", None)
        previous_workspace_fingerprint = getattr(getattr(self, "prefix_state", None), "workspace_fingerprint", None)

        # 工作区事实相对稳定，所以这里按整体刷新；
        # 只有这些事实真的变化了，才重建完整 prefix。
        refreshed_workspace = WorkspaceContext.build(self.root)
        refreshed_workspace_fingerprint = refreshed_workspace.fingerprint()
        workspace_changed = force or refreshed_workspace_fingerprint != previous_workspace_fingerprint
        if workspace_changed:
            self.workspace = refreshed_workspace

        prefix_state = self.build_prefix() if workspace_changed or force or previous_hash is None else self.prefix_state
        prefix_changed = force or previous_hash != prefix_state.hash
        if prefix_changed:
            self._apply_prefix_state(prefix_state)

        self._last_prefix_refresh = {
            "workspace_changed": workspace_changed,
            "prefix_changed": prefix_changed,
        }
        return dict(self._last_prefix_refresh)

    def memory_text(self):
        base = self.memory.render_memory_text()
        compactions = list(self.session.get("compactions", []))
        if compactions:
            latest = compactions[-1]
            summary = str(latest.get("summary", "")).strip()
            if summary:
                base = base + "\n\nCompacted session summary:\n" + summary
        todo_text = self.todo_ledger.render_prompt()
        return base if not todo_text else base + "\n\n" + todo_text

    def _persist_memory(self):
        self.session["memory"] = self.memory.to_dict()
        self.session_path = self.session_store.save(self.session)

    # 记忆审核 / 长期化 / 自迭代已迁入 MemoryCoordinator。
    # 这里保留同名转发：cli.py 与既有测试通过 agent.<name> 调用它们。
    def memory_review_pending(self):
        return self.memory_coordinator.memory_review_pending()

    def memory_review_accept(self, record_id):
        return self.memory_coordinator.memory_review_accept(record_id)

    def memory_review_edit(self, record_id, *, topic, text):
        return self.memory_coordinator.memory_review_edit(record_id, topic=topic, text=text)

    def memory_review_reject(self, record_id):
        return self.memory_coordinator.memory_review_reject(record_id)

    def memory_review_skip(self, record_id):
        return self.memory_coordinator.memory_review_skip(record_id)

    def memory_self_iteration_status(self):
        return self.memory_coordinator.memory_self_iteration_status()

    def memory_self_iteration_text(self):
        return self.memory_coordinator.memory_self_iteration_text()

    def memory_organize_text(self):
        return self.memory_coordinator.memory_organize_text()

    def promote_durable_memory(self, user_message, final_answer):
        return self.memory_coordinator.promote_durable_memory(user_message, final_answer)

    def run_memory_self_iteration(self):
        return self.memory_coordinator.run_memory_self_iteration()

    def extract_durable_promotions(self, user_message, final_answer):
        return self.memory_coordinator.extract_durable_promotions(user_message, final_answer)

    def reject_durable_reason(self, note_text):
        return self.memory_coordinator.reject_durable_reason(note_text)

    def render_skills(self):
        return skillslib.render_skills_list(self.skills)

    def invoke_skill(self, name, arguments=""):
        return skills_runtime.invoke_skill(self, name, arguments)

    @staticmethod
    def _safe_user_home():
        try:
            return Path.home()
        except RuntimeError:
            return None

    @staticmethod
    def _infer_provider_name(model_client):
        """从 model_client 类名推断 provider 名称。"""
        cls_name = type(model_client).__name__
        if "Ollama" in cls_name:
            return "ollama"
        if "Anthropic" in cls_name:
            return "anthropic"
        if "ChatCompletions" in cls_name:
            return "chat-completions"
        if "OpenAI" in cls_name:
            return "openai"
        return ""

    def spawn_worker(self, description, prompt, subagent_type="worker", write_scope=None):
        return self.worker_manager.spawn(description, prompt, subagent_type=subagent_type, write_scope=write_scope)

    def render_workers(self):
        items = self.worker_manager.to_dict().get("items", [])
        if not items:
            return "Agents:\n- none"
        return "\n".join(
            ["Agents:", *[f"- {item['id']} [{item['status']}] {item['description']}" for item in items]]
        )

    def history_text(self):
        history = self.session["history"]
        if not history:
            return "- empty"

        lines = []
        seen_reads = set()
        recent_start = max(0, len(history) - 6)
        for index, item in enumerate(history):
            recent = index >= recent_start
            if item["role"] == "tool" and item["name"] == "read_file" and not recent:
                path = str(item["args"].get("path", ""))
                if path in seen_reads:
                    continue
                seen_reads.add(path)

            if item["role"] == "tool":
                limit = 900 if recent else 180
                lines.append(f"[tool:{item['name']}] {json.dumps(item['args'], sort_keys=True)}")
                lines.append(clip(item["content"], limit))
            else:
                limit = 900 if recent else 220
                lines.append(f"[{item['role']}] {clip(item['content'], limit)}")

        return clip("\n".join(lines), MAX_HISTORY)

    def feature_enabled(self, name):
        return bool(self.feature_flags.get(str(name), False))

    def prompt(self, user_message):
        prompt, _ = self._build_prompt_and_metadata(user_message)
        return prompt

    def record(self, item):
        item = dict(item)
        if item.get("role") in {"user", "assistant", "tool"}:
            task_state = getattr(self, "current_task_state", None)
            item.setdefault("run_id", getattr(task_state, "run_id", "") or "manual")
            item.setdefault("turn_id", getattr(task_state, "task_id", "") or "manual")
        self.session["history"].append(item)
        self.session_path = self.session_store.save(self.session)

    @staticmethod
    def _estimate_tokens(text):
        from .core.context_usage import estimate_tokens
        return estimate_tokens(text)

    def context_usage(self, prompt_metadata=None):
        from .core.context_usage import ContextUsageAnalyzer

        metadata = prompt_metadata or self.last_prompt_metadata or {}
        usage = ContextUsageAnalyzer(self).analyze(metadata)
        usage["auto_compacted"] = bool(metadata.get("auto_compacted", False)) if isinstance(metadata, dict) else False
        usage["budget_reductions"] = list(metadata.get("budget_reductions", [])) if isinstance(metadata, dict) else []
        return usage

    def compact_history(self, trigger="manual"):
        pre_text = self.history_text()
        pre_tokens = self._estimate_tokens(pre_text)
        history = list(self.session.get("history", []))
        if len(history) <= 8:
            summary = "No old history needed compaction."
            retained = history
        else:
            older = history[:-6]
            retained = history[-6:]
            parts = []
            for item in older[-12:]:
                role = str(item.get("role", ""))
                content = str(item.get("content", ""))
                if item.get("role") == "tool":
                    content = f"{item.get('name', 'tool')} {item.get('args', {})}: {content}"
                parts.append(f"[{role}] {clip(content, 140)}")
            summary = "\n".join(parts) or "Older session history was compacted."
        self.session["history"] = retained
        compaction = {
            "trigger": str(trigger),
            "created_at": now(),
            "summary": summary,
            "pre_tokens": pre_tokens,
            "post_tokens": self._estimate_tokens("\n".join(str(item.get("content", "")) for item in retained)),
        }
        self.session.setdefault("compactions", []).append(compaction)
        self.session_path = self.session_store.save(self.session)
        self.emit_session_event("compaction_created", **compaction)
        return compaction

    def looks_sensitive_env_name(self, name):
        return self._secret_sanitizer.looks_sensitive_env_name(name)

    def is_secret_env_name(self, name):
        return self._secret_sanitizer.is_secret_env_name(name)

    def configured_secret_env_items(self):
        return self._secret_sanitizer.configured_secret_env_items()

    def detected_secret_env_items(self):
        return self._secret_sanitizer.detected_secret_env_items()

    def secret_env_summary(self):
        return self._secret_sanitizer.secret_env_summary()

    def detected_secret_env_summary(self):
        return self._secret_sanitizer.detected_secret_env_summary()

    def redact_text(self, text):
        return self._secret_sanitizer.redact_text(text)

    def redact_artifact(self, value, key=None):
        return self._secret_sanitizer.redact_artifact(value, key=key)

    def shell_env(self):
        return self._secret_sanitizer.shell_env()

    def prompt_metadata(self, user_message, prompt):
        _, metadata = self._build_prompt_and_metadata(user_message)
        return metadata

    def _build_prompt_and_metadata(self, user_message):
        refresh = self.refresh_prefix()
        self.resume_state = self.evaluate_resume_state()
        prompt, metadata = self.context_manager.build(user_message)
        # 这里把“这轮 prompt 是怎么拼出来的”连同缓存相关状态一起记下来，
        # 后面 trace/report 才能解释清楚：为什么这一轮 prefix 变了、缓存有没有命中。
        metadata.update(
            {
                "prefix_chars": len(self.prefix),
                "workspace_chars": len(self.workspace.text()),
                "memory_chars": len(self.memory_text()),
                "history_chars": len(self.history_text()),
                "request_chars": len(user_message),
                "tool_count": len(self.tools),
                "workspace_docs": len(self.workspace.project_docs),
                "recent_commits": len(self.workspace.recent_commits),
                "prefix_hash": self.prefix_state.hash,
                "prompt_cache_key": self.prefix_state.hash,
                "workspace_fingerprint": self.prefix_state.workspace_fingerprint,
                "tool_signature": self.prefix_state.tool_signature,
                "workspace_changed": refresh["workspace_changed"],
                "prefix_changed": refresh["prefix_changed"],
                "prompt_cache_supported": bool(getattr(self.model_client, "supports_prompt_cache", False)),
                "resume_status": self.resume_state.get("status", CHECKPOINT_NONE_STATUS),
                "stale_summary_invalidations": int(self.resume_state.get("stale_summary_invalidations", 0)),
                "stale_paths": list(self.resume_state.get("stale_paths", [])),
                "runtime_identity_mismatch_fields": list(self.resume_state.get("runtime_identity_mismatch_fields", [])),
            }
        )
        metadata.update(self.detected_secret_env_summary())
        metadata["context_usage"] = self.context_usage(metadata)
        return prompt, metadata

    def emit_trace(self, task_state, event, payload=None):
        payload = self.redact_artifact(payload or {})
        payload["event"] = event
        payload["created_at"] = now()
        payload.setdefault("phase", self._trace_phase(event))
        payload.setdefault("status", payload.get("tool_status", "ok" if "error" not in event else "error"))
        run_id = getattr(task_state, "run_id", "")
        payload.setdefault("run_id", run_id)
        payload.setdefault("turn_id", getattr(task_state, "task_id", ""))
        # Within a run, each event links to the previous event's span (a chain).
        # A child run additionally carries the parent run/span it inherited at
        # construction time (parent_run_id / inherited_parent_span_id), which
        # joins the two traces across runs.
        previous_span = self._last_trace_span_id.get(run_id, "")
        payload.setdefault("parent_span_id", previous_span)
        self._trace_seq += 1
        payload.setdefault("span_id", f"span_{self._trace_seq:06d}")
        self._last_trace_span_id[run_id] = payload["span_id"]
        payload.setdefault("parent_run_id", self.parent_run_id)
        payload.setdefault("inherited_parent_span_id", self.parent_span_id)
        payload.setdefault("artifact_paths", list(payload.get("affected_paths", []) or []))
        payload.setdefault("duration_ms", int(payload.get("duration_ms", 0) or 0))
        payload.setdefault("error_type", str(payload.get("tool_error_code", "") or ""))
        # trace 是运行中的逐事件时间线，适合回答“这一轮 agent 到底做了什么”。
        self.run_store.append_trace(task_state, payload)
        return payload

    @staticmethod
    def _trace_phase(event):
        if str(event).startswith("model"):
            return "model"
        if str(event).startswith("tool"):
            return "tool"
        if "checkpoint" in str(event):
            return "checkpoint"
        return "runtime"

    def capture_workspace_snapshot(self):
        snapshot = {}
        for path in self.root.rglob("*"):
            try:
                relative_parts = path.relative_to(self.root).parts
            except ValueError:
                continue
            if any(part in IGNORED_PATH_NAMES for part in relative_parts):
                continue
            if not path.is_file():
                continue
            try:
                snapshot[path.relative_to(self.root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                continue
        return snapshot

    @staticmethod
    def diff_workspace_snapshots(before, after):
        changed_paths = []
        summaries = []
        all_paths = sorted(set(before) | set(after))
        for path in all_paths:
            if before.get(path) == after.get(path):
                continue
            changed_paths.append(path)
            if path not in before:
                summaries.append(f"created:{path}")
            elif path not in after:
                summaries.append(f"deleted:{path}")
            else:
                summaries.append(f"modified:{path}")
        return changed_paths, summaries

    def create_checkpoint(self, task_state, user_message, trigger):
        state = self.checkpoint_state()
        current = self.current_checkpoint()
        recent_files = self.memory.to_dict()["working"]["recent_files"]
        checkpoint = build_checkpoint(
            task_state,
            user_message,
            trigger,
            recent_files,
            lambda path: memorylib.file_freshness(path, self.root),
            current.get("checkpoint_id", "") if current else "",
            self.current_runtime_identity(),
        )
        checkpoint_id = checkpoint["checkpoint_id"]
        state["items"][checkpoint_id] = checkpoint
        state["current_id"] = checkpoint_id
        task_state.checkpoint_id = checkpoint_id
        self.session["runtime_identity"] = checkpoint["runtime_identity"]
        self.session_path = self.session_store.save(self.session)
        return checkpoint

    def infer_next_step(self, task_state):
        return infer_next_step(task_state)

    def update_memory_after_tool(self, name, args, result):
        """把少量高价值工具结果沉淀到 working memory。

        为什么存在：
        并不是每个工具结果都值得长期带进下一轮 prompt。完整结果已经进了
        `history`，这里只挑少量“下一轮大概率还会用到”的事实做提纯，
        例如最近读写过哪些文件、某个文件读出来的短摘要。

        输入 / 输出：
        - 输入：工具名 `name`、参数 `args`、执行结果 `result`
        - 输出：无显式返回值，副作用是更新 `self.memory`

        在 agent 链路里的位置：
        它发生在 `run_tool()` 真正执行完工具之后、下一轮 prompt 组装之前。
        也就是说：工具结果先进入完整历史，再由这个函数择优沉淀成轻量记忆。
        """
        if not self.feature_enabled("memory"):
            return
        path = args.get("path")
        if not path:
            return

        canonical_path = self.memory.canonical_path(path)
        # 不是所有工具结果都进入工作记忆。
        # 读文件会生成摘要；写文件/patch 会让旧摘要失效，因为它们可能过期了。
        if name in {"read_file", "write_file", "patch_file"}:
            self.memory.remember_file(canonical_path)
        if name == "read_file":
            summary = memorylib.summarize_read_result(
                result,
                complete_file=self._read_file_args_cover_complete_file(args),
            )
            self.memory.set_file_summary(canonical_path, summary)
            self.memory.append_note(summary, tags=(canonical_path,), source=canonical_path)
        elif name in {"write_file", "patch_file"}:
            self.memory.invalidate_file_summary(canonical_path)

    def _read_file_args_cover_complete_file(self, args):
        try:
            start = int(args.get("start", 1))
            end = int(args.get("end", 200))
        except (TypeError, ValueError):
            return False
        if start != 1:
            return False
        path = args.get("path")
        if not path:
            return False
        resolved = memorylib.resolve_workspace_path(path, self.root)
        if resolved is None or not resolved.is_file():
            return False
        try:
            line_count = len(resolved.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            return False
        return end >= line_count

    def note_tool(self, name, args, result):
        self.update_memory_after_tool(name, args, result)

    def record_process_note_for_tool(self, name, metadata):
        status = str(metadata.get("tool_status", "")).strip()
        if status not in {"partial_success", "error", "rejected"}:
            return
        affected_paths = [str(path).strip() for path in metadata.get("affected_paths", []) if str(path).strip()]
        path_text = ", ".join(affected_paths) or "workspace"
        if status == "partial_success":
            text = f"{name} partial_success on {path_text}; inspect diff before retry"
        elif status == "error":
            text = f"{name} error on {path_text}; check the failure before retry"
        else:
            text = f"{name} rejected; choose a different action before retry"
        tags = ["process", status, *affected_paths]
        self.memory.append_note(text, tags=tuple(tags), source=name, kind="process")
        self.session["memory"] = self.memory.to_dict()

    def _record_runtime_reminder(self, name, metadata):
        status = str(metadata.get("tool_status", "")).strip()
        if status not in {"partial_success", "error", "rejected"}:
            return
        reminder = {
            "tool": str(name),
            "status": status,
            "tool_error_code": str(metadata.get("tool_error_code", "")),
            "affected_paths": list(metadata.get("affected_paths", []) or []),
            "created_at": now(),
        }
        self.runtime_reminders.append(reminder)
        if self.current_task_state is not None:
            self.current_task_state.runtime_reminders = list(self.runtime_reminders)

    def ask(self, user_message):
        """执行一次完整的 agent 回合，直到产出最终答案或命中停止条件。

        为什么存在：
        `ask()` 是整个 runtime 的总调度器。它把“用户提一个请求”扩展成一条
        可持续推进的控制循环：记录会话、组 prompt、调用模型、执行工具、
        写 trace/report、更新状态，直到模型给出最终答案或系统主动停下。

        输入 / 输出：
        - 输入：`user_message`，即用户这一次的任务描述
        - 输出：字符串形式的最终回答；如果中途达到步数上限或重试上限，
          返回的是一条停止原因说明

        在 agent 链路里的位置：
        它是 CLI 和底层工具/模型之间的核心桥梁。CLI 收到用户输入后基本只做
        一件事：调用 `agent.ask()`。而 `ask()` 内部再去驱动 `ContextManager`
        组 prompt、`model_client.complete()` 调模型、`run_tool()` 执行动作。
        如果新人想理解 RepoHarness 是怎么“从一句话跑成一个 agent 流程”的，
        这里就是最关键的入口。
        """
        return self.engine.ask(user_message)


    def run_tool(self, name, args):
        """执行一次工具调用，并在执行前后套上完整护栏。

        为什么存在：
        在 agent 系统里，真正危险的不是“模型会不会想调用工具”，而是
        “平台有没有在执行前把边界守住”。这个函数就是工具层的总闸口：
        所有工具调用都必须先经过它，不能让模型直接碰到底层函数。

        输入 / 输出：
        - 输入：工具名 `name`，参数字典 `args`
        - 输出：字符串结果。无论是成功结果还是错误信息，都会统一返回文本，
          这样模型下一轮都能继续消费这份反馈。

        在 agent 链路里的位置：
        它位于 `ask()` 的“模型决定要调用工具”之后，是控制循环里真正把模型
        意图落到外部世界的一步。因此这里串起了几乎所有安全与可控设计：
        工具是否存在、参数是否合法、是否重复、是否需要审批、执行结果是否裁剪、
        是否需要回写记忆。
        """
        return core_tool_executor.run_tool(self, name, args)

    def repeated_tool_call(self, name, args):
        # agent 很常见的一种坏循环，是在没有新信息的情况下反复发起同一调用。
        # 这里提前挡掉最简单的这种循环。
        tool_events = [item for item in self.session["history"] if item["role"] == "tool"]
        if len(tool_events) < 2:
            return False
        recent = tool_events[-2:]
        return all(item["name"] == name and item["args"] == args for item in recent)

    def _finalize_runtime_evidence(self, task_state):
        graph = runtime_evidence.artifact_graph(self.root, list(getattr(self, "_run_changed_paths", [])))
        suggestions = runtime_evidence.verifier_suggestions(self.root)
        task_state.artifact_graph = graph
        task_state.verifier_suggestions = suggestions
        task_state.runtime_reminders = list(getattr(self, "runtime_reminders", []))
        return graph, suggestions

    @staticmethod
    def new_task_id():
        return "task_" + id_timestamp() + "-" + uuid.uuid4().hex[:6]

    @staticmethod
    def new_run_id():
        return "run_" + id_timestamp() + "-" + uuid.uuid4().hex[:6]

    def build_report(self, task_state):
        # report 是一次运行的最终摘要；
        # 和 trace 的区别在于，trace 关注过程，report 关注结果与关键指标。
        graph, suggestions = self._finalize_runtime_evidence(task_state)
        return {
            "run_id": task_state.run_id,
            "task_id": task_state.task_id,
            "status": task_state.status,
            "stop_reason": task_state.stop_reason,
            "verification_status": task_state.verification_status,
            "verification_evidence": list(task_state.verification_evidence),
            "final_answer": task_state.final_answer,
            "tool_steps": task_state.tool_steps,
            "attempts": task_state.attempts,
            "checkpoint_id": task_state.checkpoint_id,
            "resume_status": task_state.resume_status,
            "task_state": task_state.to_dict(),
            "prompt_metadata": self.last_prompt_metadata,
            **self.memory_outcome.report_dict(),
            "todos": self.todo_ledger.to_dict(),
            "todo_changes": list(getattr(task_state, "todo_changes", []) or self.session.get("todo_changes", [])),
            "workers": self.worker_manager.to_dict(),
            "artifact_graph": graph,
            "verifier_suggestions": suggestions,
            "runtime_reminders": list(task_state.runtime_reminders),
            "redacted_env": self.detected_secret_env_summary(),
        }

    def tool_example(self, name):
        return toolkit.tool_example(name)

    def validate_tool(self, name, args):
        """把通用工具校验和 runtime 级额外约束串起来。"""
        toolkit.validate_tool(self, name, args)
        if name == "delegate" and self.depth >= self.max_depth:
            raise ValueError("delegate depth exceeded")

    def tool_list_files(self, args):
        return toolkit.tool_list_files(self, args)

    def tool_read_file(self, args):
        return toolkit.tool_read_file(self, args)

    def tool_search(self, args):
        return toolkit.tool_search(self, args)

    def tool_run_shell(self, args):
        return toolkit.tool_run_shell(self, args)

    def tool_write_file(self, args):
        return toolkit.tool_write_file(self, args)

    def tool_patch_file(self, args):
        return toolkit.tool_patch_file(self, args)

    def tool_delegate(self, args):
        return toolkit.tool_delegate(self, args)

    def tool_todo_add(self, args):
        return toolkit.tool_todo_add(self, args)

    def tool_todo_update(self, args):
        return toolkit.tool_todo_update(self, args)

    def tool_todo_list(self, args):
        return toolkit.tool_todo_list(self, args)

    def approve(self, name, args):
        if self.read_only:
            return False
        if self.approval_policy == "auto":
            return True
        if self.approval_policy == "never":
            return False
        # 会话级信任：已确认的工具本次会话内自动放行
        if name in self._trusted_tools:
            return True

        # Rich 风格输入（如果 display 可用）
        display = getattr(self, "_display", None)
        args_summary = json.dumps(args, ensure_ascii=True)[:80]
        if display:
            answer = display.prompt_choice(
                f"approve {name} {args_summary}?",
                ["y", "n", "a"],
            )
        else:
            try:
                answer = input(f"approve {name} {args_summary}? [y/N/a(llow this session)] ")
            except EOFError:
                return False
            answer = answer.strip().lower()

        if answer in {"y", "yes"}:
            return True
        if answer in {"a", "all", "always"}:
            self._trusted_tools.add(name)
            return True
        return False

    @staticmethod
    def parse(raw):
        """把模型原始输出解析成 runtime 可执行的动作或最终答案。

        为什么存在：
        模型输出首先是自然语言文本，而 runtime 需要的是结构化决策：
        “这是工具调用”还是“这是最终答案”。如果没有这层解析，后面的工具校验、
        审批和执行链路就没法可靠工作。

        输入 / 输出：
        - 输入：模型返回的原始文本 `raw`
        - 输出：`(kind, payload)`，其中 `kind` 可能是 `tool`、`final`、`retry`

        在 agent 链路里的位置：
        它位于 `model_client.complete()` 之后、`run_tool()` 之前，是模型输出
        进入平台控制流的第一道结构化关口。
        """
        raw = str(raw)
        # 这里支持两种工具格式：
        # 1. <tool>...</tool> 里包 JSON，适合简短调用
        # 2. XML 风格属性/子标签，适合写文件这类多行内容
        if "<tool" in raw and ("<final>" not in raw or raw.find("<tool") < raw.find("<final>")):
            tool_matches = list(re.finditer(r"<tool(?P<attrs>[^>]*)>(?P<body>.*?)</tool>", raw, re.S))
            if len(tool_matches) > 1:
                payloads = []
                for match in tool_matches:
                    payload = RepoHarness.parse_tool_match(match)
                    if payload is None:
                        return "retry", RepoHarness.retry_notice("model returned malformed tool output")
                    payloads.append(payload)
                return "tools", payloads
        if "<tool>" in raw and ("<final>" not in raw or raw.find("<tool>") < raw.find("<final>")):
            body = RepoHarness.extract(raw, "tool")
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                return "retry", RepoHarness.retry_notice("model returned malformed tool JSON")
            if not isinstance(payload, dict):
                return "retry", RepoHarness.retry_notice("tool payload must be a JSON object")
            if not str(payload.get("name", "")).strip():
                return "retry", RepoHarness.retry_notice("tool payload is missing a tool name")
            args = payload.get("args", {})
            if args is None:
                payload["args"] = {}
            elif not isinstance(args, dict):
                return "retry", RepoHarness.retry_notice()
            return "tool", payload
        if "<tool" in raw and ("<final>" not in raw or raw.find("<tool") < raw.find("<final>")):
            payload = RepoHarness.parse_xml_tool(raw)
            if payload is not None:
                return "tool", payload
            return "retry", RepoHarness.retry_notice()
        if "<final>" in raw:
            final = RepoHarness.extract(raw, "final").strip()
            if final:
                return "final", final
            return "retry", RepoHarness.retry_notice("model returned an empty <final> answer")
        raw = raw.strip()
        if raw:
            return "final", raw
        return "retry", RepoHarness.retry_notice("model returned an empty response")

    @staticmethod
    def parse_tool_match(match):
        attrs = RepoHarness.parse_attrs(match.group("attrs"))
        body = match.group("body")
        if not attrs:
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                return None
            if not isinstance(payload, dict):
                return None
            if not str(payload.get("name", "")).strip():
                return None
            args = payload.get("args", {})
            if args is None:
                payload["args"] = {}
            elif not isinstance(args, dict):
                return None
            return payload
        return RepoHarness.parse_xml_tool(match.group(0))

    @staticmethod
    def retry_notice(problem=None):
        prefix = "Runtime notice"
        if problem:
            prefix += f": {problem}"
        else:
            prefix += ": model returned malformed tool output"
        return (
            f"{prefix}. Reply with a valid <tool> call or a non-empty <final> answer. "
            'For multi-line files, prefer <tool name="write_file" path="file.py"><content>...</content></tool>.'
        )

    @staticmethod
    def parse_xml_tool(raw):
        match = re.search(r"<tool(?P<attrs>[^>]*)>(?P<body>.*?)</tool>", raw, re.S)
        if not match:
            return None
        attrs = RepoHarness.parse_attrs(match.group("attrs"))
        name = str(attrs.pop("name", "")).strip()
        if not name:
            return None

        body = match.group("body")
        args = dict(attrs)
        for key in ("content", "old_text", "new_text", "command", "task", "pattern", "path"):
            if f"<{key}>" in body:
                args[key] = RepoHarness.extract_raw(body, key)

        body_text = body.strip("\n")
        if name == "write_file" and "content" not in args and body_text:
            args["content"] = body_text
        if name == "delegate" and "task" not in args and body_text:
            args["task"] = body_text.strip()
        return {"name": name, "args": args}

    @staticmethod
    def parse_attrs(text):
        attrs = {}
        for match in re.finditer(r"""([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:"([^"]*)"|'([^']*)')""", text):
            attrs[match.group(1)] = match.group(2) if match.group(2) is not None else match.group(3)
        return attrs

    @staticmethod
    def extract(text, tag):
        start_tag = f"<{tag}>"
        end_tag = f"</{tag}>"
        start = text.find(start_tag)
        if start == -1:
            return text
        start += len(start_tag)
        end = text.find(end_tag, start)
        if end == -1:
            return text[start:].strip()
        return text[start:end].strip()

    @staticmethod
    def extract_raw(text, tag):
        start_tag = f"<{tag}>"
        end_tag = f"</{tag}>"
        start = text.find(start_tag)
        if start == -1:
            return text
        start += len(start_tag)
        end = text.find(end_tag, start)
        if end == -1:
            return text[start:]
        return text[start:end]

    def reset(self):
        self.session["history"] = []
        self.session["memory"].clear()
        self.session["memory"].update(memorylib.default_memory_state())
        self.memory = memorylib.LayeredMemory(self.session["memory"], workspace_root=self.root)
        self.session_store.save(self.session)

    def path(self, raw_path):
        path = Path(raw_path)
        path = path if path.is_absolute() else self.root / path
        resolved = path.resolve()
        # 所有文件类工具都被锚定在 workspace root 之下。
        # 这样既能防住 "../" 逃逸，也能防住符号链接解析后跳出仓库。
        if os.path.commonpath([str(self.root), str(resolved)]) != str(self.root):
            raise ValueError(f"path escapes workspace: {raw_path}")
        return resolved



