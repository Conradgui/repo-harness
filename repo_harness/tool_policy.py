"""Lightweight tool-use policy for RepoHarness."""

import posixpath
import shlex
from pathlib import Path


WORKSPACE_READ_COMMANDS = {"cat", "less", "head", "tail", "grep", "rg", "find", "ls"}


class ToolPolicyRejection(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


class ToolPolicy:
    def __init__(self, agent):
        self.agent = agent
        self._fresh_reads = set()

    def check(self, name, args):
        if self._is_repeated(name, args):
            raise ToolPolicyRejection(
                "repeated_identical_call",
                f"error: repeated identical tool call for {name}; choose a different tool or return a final answer",
            )
        if name == "run_shell":
            self._check_run_shell(args)
        if name in {"write_file", "patch_file"}:
            self._check_fresh_read(name, args)

    def record_result(self, name, args, metadata):
        if str(metadata.get("tool_status", "")) not in {"ok", "partial_success"}:
            return
        if name == "read_file":
            path = self._relative_path(args.get("path", ""))
            if path:
                self._fresh_reads.add(path)
            return
        if name in {"write_file", "patch_file"}:
            path = self._relative_path(args.get("path", ""))
            if path:
                self._fresh_reads.discard(path)
            return
        if name == "run_shell" and metadata.get("workspace_changed"):
            self._fresh_reads.clear()

    def _is_repeated(self, name, args):
        tool_events = [item for item in self.agent.session["history"] if item["role"] == "tool"]
        if len(tool_events) < 2:
            return False
        recent = tool_events[-2:]
        return all(item["name"] == name and item["args"] == args for item in recent)

    def _check_run_shell(self, args):
        command = str(args.get("command", "")).strip()
        if not command:
            return
        command_name = self._primary_command_name(command)
        if command_name in WORKSPACE_READ_COMMANDS:
            raise ToolPolicyRejection(
                "tool_policy_workspace_read",
                "error: tool policy rejected run_shell workspace read/search; use search/read_file/list_files instead",
            )

    def _primary_command_name(self, command):
        first_segment = command.split("|", 1)[0].strip()
        try:
            parts = shlex.split(first_segment, posix=True)
        except ValueError:
            parts = first_segment.split()
        if not parts:
            return ""
        return Path(parts[0]).name.lower()

    def _check_fresh_read(self, name, args):
        path = self.agent.path(args.get("path", ""))
        if not path.exists():
            return
        rel = self._relative_path(args.get("path", ""))
        if rel not in self._fresh_reads:
            raise ToolPolicyRejection(
                "tool_policy_fresh_read_required",
                f"error: tool policy rejected {name}; perform a fresh read_file on {rel} before modifying it",
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
