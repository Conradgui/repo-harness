"""Unified tool permission decisions for RepoHarness."""

from dataclasses import dataclass


READ_ONLY_TOOLS = {"list_files", "read_file", "search", "todo_list", "ask_user", "delegate"}
WRITE_TOOLS = {"write_file", "patch_file"}


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


class PermissionChecker:
    def __init__(self, runtime):
        self.runtime = runtime

    def check(self, name, args=None):
        args = args or {}
        profile = getattr(self.runtime, "tool_profile", "default")
        mode = getattr(self.runtime, "runtime_mode", "default")
        risky = bool(self.runtime.tools.get(name, {}).get("risky", False))

        if mode == "plan":
            plan_denial = self._plan_mode_denial(name, args)
            if plan_denial:
                return PermissionDecision.deny(plan_denial, security_event_type=plan_denial, profile="plan")
            if name in READ_ONLY_TOOLS or name in {"todo_add", "todo_update"}:
                return PermissionDecision.allow("plan_allowed", profile="plan")

        if getattr(self.runtime, "read_only", False) and risky:
            return PermissionDecision.deny("read_only_block", security_event_type="read_only_block", profile=profile)

        if risky and getattr(self.runtime, "approval_policy", "ask") == "never":
            return PermissionDecision.deny("approval_denied", security_event_type="approval_denied", profile=profile)

        if not risky:
            return PermissionDecision.allow("read_only", profile=profile)
        return PermissionDecision.allow("approval_available", profile=profile)

    def _plan_mode_denial(self, name, args):
        if name == "run_shell":
            return "plan_mode_tool_denied"
        if name == "delegate":
            return ""
        if name not in WRITE_TOOLS:
            return ""
        target = str((args or {}).get("path", "")).strip().replace("\\", "/")
        active = str(getattr(self.runtime, "active_plan_path", "") or "").strip().replace("\\", "/")
        if target and active and target == active:
            return ""
        return "plan_mode_path_mismatch"
