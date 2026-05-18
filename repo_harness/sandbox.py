"""Run_shell sandbox controls for RepoHarness."""

from dataclasses import dataclass
import shutil
import subprocess
import textwrap
from pathlib import Path


@dataclass(frozen=True)
class SandboxConfig:
    mode: str = "off"
    backend: str = "native"
    workspace_write: bool = True
    excluded_commands: tuple[str, ...] = ()
    extra_readonly_paths: tuple[str, ...] = ()
    deny_read: tuple[str, ...] = ()
    deny_write: tuple[str, ...] = ()

    @property
    def enabled(self):
        return self.mode != "off"


class SandboxRunner:
    def __init__(self, config=None):
        self.config = config or SandboxConfig()
        self.which = shutil.which

    def run(self, agent, command, timeout, runner):
        mode = str(self.config.mode or "off").strip()
        backend = str(self.config.backend or "native").strip()
        if mode == "off" or self._command_is_excluded(command):
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
        if backend in {"auto", "native"}:
            return runner(command, timeout)
        if backend == "bubblewrap":
            return self._run_bubblewrap(command, timeout, agent, runner)
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

    def _command_is_excluded(self, command):
        excluded = getattr(self.config, "excluded_commands", ()) or ()
        head = str(command or "").strip().split(maxsplit=1)[0].lower()
        return any(head == str(item).lower() for item in excluded)

    def _run_bubblewrap(self, command, timeout, agent, runner):
        backend_path = self.which("bwrap") or self.which("bubblewrap")
        if not backend_path:
            return runner(command, timeout)
        root = Path(agent.root)
        bind_mode = "--bind" if self.config.workspace_write else "--ro-bind"
        argv = [
            backend_path,
            "--die-with-parent",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            bind_mode,
            str(root),
            str(root),
            "--chdir",
            str(root),
            "--",
            "/bin/sh",
            "-lc",
            str(command),
        ]
        result = subprocess.run(
            argv,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=agent.shell_env(),
        )
        return format_completed_process(result)


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
