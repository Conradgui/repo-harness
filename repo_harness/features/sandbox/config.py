"""Sandbox configuration exports."""

from ...sandbox import SandboxConfig

SANDBOX_MODES = {"off", "best_effort", "read_only", "required"}
SANDBOX_BACKENDS = {"native", "auto", "bubblewrap"}

__all__ = ["SANDBOX_BACKENDS", "SANDBOX_MODES", "SandboxConfig"]

