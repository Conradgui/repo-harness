"""Minimal run_shell sandbox controls for RepoHarness."""

from dataclasses import dataclass
import shutil
import subprocess
import textwrap


@dataclass(frozen=True)
class SandboxConfig:
    mode: str = "off"
    backend: str = "native"


class SandboxRunner:
    def __init__(self, config=None):
        self.config = config or SandboxConfig()
        self.which = shutil.which

    def run(self, agent, command, timeout, runner):
        mode = str(self.config.mode or "off").strip()
        backend = str(self.config.backend or "native").strip()
        if mode == "off":
            return None
        if mode == "read_only":
            raise RuntimeError("sandbox read_only blocks run_shell")
        if mode not in {"best_effort", "required"}:
            raise RuntimeError(f"unsupported sandbox mode: {mode}")
        unavailable = self._backend_unavailable(backend)
        if unavailable:
            if hasattr(agent, "emit_session_event"):
                agent.emit_session_event(
                    "sandbox_unavailable",
                    mode=mode,
                    backend=backend,
                    reason=unavailable,
                    command=command,
                )
            if mode == "required":
                raise RuntimeError("sandbox required but unavailable")
            return runner(command, timeout)
        return runner(command, timeout)

    def _backend_unavailable(self, backend):
        if backend in {"", "native"}:
            return ""
        if backend == "auto":
            return ""
        if backend == "bubblewrap":
            if self.which("bwrap") or self.which("bubblewrap"):
                return ""
            return "bubblewrap not found"
        return f"unsupported backend: {backend}"


def format_completed_process(result):
    return textwrap.dedent(
        f"""\
        exit_code: {result.returncode}
        stdout:
        {result.stdout.strip() or "(empty)"}
        stderr:
        {result.stderr.strip() or "(empty)"}
        """
    ).strip()


def run_platform_shell(command, cwd, timeout, env):
    result = subprocess.run(
        command,
        cwd=cwd,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    return format_completed_process(result)
