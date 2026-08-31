"""Unified runtime permission decisions for tool execution."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    reason: str = ""
    security_event_type: str = ""
    profile: str = "default"

    @classmethod
    def allow(cls, reason="", profile="default"):
        return cls(True, str(reason), "", str(profile))

    @classmethod
    def deny(cls, reason, security_event_type="", profile="default"):
        return cls(False, str(reason), str(security_event_type), str(profile))

    @property
    def decision(self):
        return "allow" if self.allowed else "deny"


class PermissionChecker:
    def __init__(self, runtime):
        self.runtime = runtime

    def check(self, tool_or_name, args=None):
        tool = self._tool(tool_or_name)
        args = args or {}
        profile = getattr(self.runtime, "active_tool_profile", None)
        profile_name = getattr(profile, "name", getattr(self.runtime, "tool_profile", "default"))
        if profile is not None and not profile.allows(tool.name):
            if profile_name == "plan":
                return PermissionDecision.deny(
                    "plan_mode_tool_not_allowed",
                    "plan_mode_write_guard",
                    profile=profile_name,
                )
            return PermissionDecision.deny("tool_not_allowed", profile=profile_name)

        if getattr(self.runtime, "runtime_mode", "default") == "plan":
            return self._check_plan(tool, args, profile_name)
        if tool.name == "run_shell" and self._shell_blocked_by_sandbox(args):
            # SandboxRunner raises for this too, which reaches the model as a
            # generic tool failure. Deciding it here instead means the refusal
            # carries a reason and shows up in the permission matrix.
            return PermissionDecision.deny(
                "sandbox_read_only",
                "sandbox_guard",
                profile=profile_name,
            )
        if tool.name in {"write_file", "patch_file"}:
            state_dir_denial = self._runtime_state_write_denied(args, profile_name)
            if state_dir_denial is not None:
                return state_dir_denial
            if getattr(self.runtime, "write_scope", ()):
                return self._check_write_scope(tool, args, profile_name)
        if tool.read_only:
            return PermissionDecision.allow("read_only", profile=profile_name)
        if getattr(self.runtime, "read_only", False):
            return PermissionDecision.deny("approval_denied", "read_only_block", profile=profile_name)
        approval_policy = getattr(self.runtime, "approval_policy", "ask")
        if approval_policy == "auto":
            return PermissionDecision.allow("approval_auto", profile=profile_name)
        if approval_policy == "never":
            return PermissionDecision.deny("approval_denied", "approval_denied", profile=profile_name)
        return PermissionDecision.allow("approval_required", profile=profile_name)

    def _shell_blocked_by_sandbox(self, args):
        """read_only means no shell command runs. There is no exemption.

        `excluded_commands` used to bypass this, which made the refusal depend
        on being able to tell from a command string that it can only do one
        thing. Three rounds of filtering were each defeated -- most recently by
        `git status/../whoami`, which contains no shell metacharacter at all and
        still runs an arbitrary program through git's dashed-external dispatch.
        See ADR-007.
        """
        del args
        config = getattr(self.runtime, "sandbox_config", None)
        return str(getattr(config, "mode", "") or "").strip() == "read_only"

    def _tool(self, tool_or_name):
        if hasattr(tool_or_name, "name"):
            return tool_or_name
        name = str(tool_or_name)
        raw = self.runtime.tools.get(name)
        if hasattr(raw, "name"):
            return raw

        class _Tool:
            def __init__(self, tool_name, spec):
                self.name = tool_name
                self.risky = bool((spec or {}).get("risky", False))
                self.read_only = not self.risky

        return _Tool(name, raw or {})

    def _check_plan(self, tool, args, profile_name):
        if tool.read_only:
            return PermissionDecision.allow("plan_read_only", profile=profile_name)
        if tool.name not in {"write_file", "patch_file"}:
            return PermissionDecision.deny(
                "plan_mode_tool_not_allowed",
                "plan_mode_write_guard",
                profile=profile_name,
            )
        requested = self.runtime.path(args.get("path", ""))
        active = self.runtime.path(getattr(self.runtime, "active_plan_path", ""))
        if Path(requested) != Path(active):
            return PermissionDecision.deny(
                "plan_mode_path_mismatch",
                "plan_mode_write_guard",
                profile=profile_name,
            )
        return PermissionDecision.allow("plan_artifact_write", profile=profile_name)

    def _runtime_state_write_denied(self, args, profile_name):
        """``.repo-harness/`` is harness-owned runtime state, never tool-writable.

        Durable memory, review queues, sessions, run records and skills live
        there. The harness writes them only through its own modules (memory
        governance, run store, session store, plan mode), so a model tool
        writing this directory bypasses every governance chain -- including
        secret filtering -- and the written notes reach later prompts through
        memory recall. The guard is evaluated before write_scope on purpose:
        no explicit scope grant may re-open a governance directory, the same
        way plan-mode artifacts stay writable only through the plan path above.
        """
        try:
            requested = self.runtime.path(args.get("path", ""))
        except ValueError:
            # Path escapes the workspace; write_scope and the tool layer
            # reject it with their own reasons. Do not shadow that here.
            return None
        # requested comes back resolved from runtime.path(); resolve the state
        # dir too, otherwise a symlinked workspace root (e.g. /var -> /private/var
        # on macOS) makes every state-dir path look "outside" and the guard
        # silently approves the write.
        state_dir = (Path(self.runtime.root) / ".repo-harness").resolve()
        if requested == state_dir or state_dir in requested.parents:
            return PermissionDecision.deny(
                "runtime_state_write_denied",
                "state_dir_write_guard",
                profile=profile_name,
            )
        return None

    def _check_write_scope(self, tool, args, profile_name):
        requested = self.runtime.path(args.get("path", ""))
        for raw_scope in self.runtime.write_scope:
            scope = self.runtime.path(raw_scope)
            try:
                requested.relative_to(scope if scope.is_dir() else scope.parent)
            except ValueError:
                continue
            if scope.is_dir() or requested == scope or scope.name == requested.name:
                return PermissionDecision.allow("write_scope", profile=profile_name)
        return PermissionDecision.deny("write_scope_mismatch", "write_scope_guard", profile=profile_name)
