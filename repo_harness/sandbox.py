"""Run_shell sandbox controls for RepoHarness."""

import fnmatch
import shutil
import subprocess
import textwrap
from dataclasses import dataclass
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


SANDBOX_MODES = frozenset({"off", "read_only", "best_effort", "required"})

# This filter is a convenience, not a security boundary. ADR-007 records why:
# deciding from a command string that it can only do one thing is not
# achievable -- three rounds of filtering were each defeated, most recently by
# `git status/../whoami`, which contains no shell metacharacter and still runs
# an arbitrary program through git's dashed-external dispatch.
#
# It survives only under best_effort, where the user has already opted out of
# guaranteed isolation. read_only no longer consults it at all. What remains
# here catches the obvious cases on both shells (shell=True means cmd.exe on
# Windows and sh elsewhere), and nothing more should be claimed for it.
SHELL_CONTROL_CHARACTERS = frozenset(";&|<>$`\\(){}!#%^\n\r")


def _has_shell_control_character(command):
    return any(character in SHELL_CONTROL_CHARACTERS for character in str(command))


class SandboxRunner:
    def __init__(self, config=None):
        self.config = config or SandboxConfig()
        self.which = shutil.which

    def run(self, agent, command, timeout, runner):
        mode = str(self.config.mode or "off").strip()
        backend = str(self.config.backend or "native").strip()
        # Validate before anything else. A misspelled mode used to fall through
        # to the exemption, so `READ_ONLY` in a config file silently became
        # "run it unsandboxed" -- the opposite of what was written.
        if mode not in SANDBOX_MODES:
            raise RuntimeError(f"unsupported sandbox mode: {mode}")
        if mode == "off":
            return None
        # read_only is checked before the exemption: under this mode nothing
        # runs, which is what the mode name says. The exemption used to come
        # first, and no amount of filtering made that safe -- see ADR-007.
        if mode == "read_only":
            from .logging_config import get_logger

            get_logger("sandbox").debug("run_shell blocked by read_only sandbox: %s", command)
            raise RuntimeError("sandbox read_only blocks run_shell")
        if mode != "required" and self._command_is_excluded(command):
            return None
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
        if _has_shell_control_character(command):
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
            check=False,
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


