"""Tool usage policy checks above raw permission gates."""

import posixpath
import re
from dataclasses import dataclass

from . import memory as memorylib

SHELL_SEARCH_RE = re.compile(
    r"(?:^|;|&&|\|\|)\s*(?:cat|less|head|tail|grep|rg|find|ls)(?:\s|$)"
)


class ToolPolicyRejection(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = str(code)
        self.message = str(message)


@dataclass(frozen=True)
class ToolPolicyDecision:
    decision: str
    reason: str
    message: str = ""

    @classmethod
    def allow(cls, reason="policy_ok"):
        return cls("allow", reason)

    @classmethod
    def deny(cls, reason, message):
        return cls("deny", reason, message)

    @property
    def allowed(self):
        return self.decision == "allow"


class ToolPolicy:
    def __init__(self, agent):
        self.agent = agent
        self._fresh_reads = set()
        self._self_authored = set()

    def check(self, name, args):
        decision = self.decision(name, args)
        if not decision.allowed:
            raise ToolPolicyRejection(decision.reason, decision.message)

    def decision(self, name, args):
        args = args or {}
        if self.agent.runtime_mode == "plan":
            return ToolPolicyDecision.allow("plan_mode")
        if self._is_repeated(name, args):
            return ToolPolicyDecision.deny(
                "repeated_identical_call",
                f"error: repeated identical tool call for {name}; choose a different tool or return a final answer",
            )
        if name == "run_shell":
            command = str(args.get("command", "")).strip()
            if SHELL_SEARCH_RE.search(command):
                reason = "shell_search_should_use_tool" if re.search(r";|&&|\|\|", command) else "tool_policy_workspace_read"
                return ToolPolicyDecision.deny(
                    reason,
                    "error: tool policy rejected run_shell workspace read/search; run_shell is not for ordinary workspace search/read; use search/read_file/list_files first",
                )
        if name == "patch_file" and not self._has_fresh_read(args.get("path", ""), allow_self_authored=True):
            return self._prior_read_required(name, args.get("path", ""))
        if name == "write_file":
            path = self.agent.path(args.get("path", ""))
            if path.exists() and path.is_file() and not self._has_fresh_read(args.get("path", "")):
                return self._prior_read_required(name, args.get("path", ""))
        return ToolPolicyDecision.allow()

    def record_result(self, name, args, metadata):
        if str(metadata.get("tool_status", "")) not in {"ok", "partial_success"}:
            return
        rel = self._relative_path((args or {}).get("path", ""))
        if name == "read_file" and rel:
            self._fresh_reads.add(rel)
            return
        if name == "write_file" and rel:
            self._self_authored.add(rel)
            self._fresh_reads.discard(rel)
            return
        if name == "patch_file" and rel:
            self._self_authored.add(rel)
            self._fresh_reads.discard(rel)
            return
        if name == "run_shell" and metadata.get("workspace_changed"):
            self._fresh_reads.clear()
            self._self_authored.clear()

    def _is_repeated(self, name, args):
        tool_events = [item for item in self.agent.session["history"] if item["role"] == "tool"]
        if len(tool_events) < 2:
            return False
        recent = tool_events[-2:]
        return all(item["name"] == name and item["args"] == args for item in recent)

    def _has_fresh_read(self, path, *, allow_self_authored=False):
        rel = self._relative_path(path)
        if not rel:
            return False
        if rel in self._fresh_reads:
            return True
        if allow_self_authored and rel in self._self_authored:
            return True
        try:
            summary = self.agent.memory.to_dict().get("file_summaries", {}).get(rel, {})
            if summary and summary.get("freshness") == memorylib.file_freshness(rel, self.agent.root):
                return True
        except Exception:
            return False
        return False

    @staticmethod
    def _prior_read_required(tool_name, path):
        return ToolPolicyDecision.deny(
            "prior_read_required",
            f"error: {tool_name} requires a fresh read_file of {path} before modifying it",
        )

    def _relative_path(self, value):
        if not value:
            return ""
        path = self.agent.path(value)
        try:
            rel = path.relative_to(self.agent.root)
        except ValueError:
            return ""
        return posixpath.join(*rel.parts) if rel.parts else "."
