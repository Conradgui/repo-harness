"""Run_shell sandbox controls for RepoHarness."""

from dataclasses import dataclass
import fnmatch
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
        if mode == "off" or (mode != "required" and self._command_is_excluded(command)):
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
        command = str(command or "").strip()
        # 防止 shell 元字符绕过：如果命令包含子 shell 或变量展开，不跳过 sandbox
        shell_metacharacters = ("$(", "${", "`", "\\")
        if any(mc in command for mc in shell_metacharacters):
            return False
        return any(fnmatch.fnmatch(command, str(item)) for item in excluded)

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
            "--ro-bind",
            "/usr",
            "/usr",
            "--ro-bind",
            "/bin",
            "/bin",
            "--ro-bind",
            "/lib",
            "/lib",
            "--ro-bind",
            "/lib64",
            "/lib64",
            bind_mode,
            str(root),
            str(root),
        ]
        for path in self.config.extra_readonly_paths:
            argv.extend(["--ro-bind", path, path])
        for path in (*self.config.deny_read, *self.config.deny_write):
            argv.extend(["--tmpfs", path])
        argv.extend([
            "--chdir",
            str(root),
            "--",
            "/bin/sh",
            "-lc",
            str(command),
        ])
        result = subprocess.run(
            argv,
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
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


