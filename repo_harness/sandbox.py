"""Minimal run_shell sandbox controls for RepoHarness."""

from dataclasses import dataclass
import subprocess
import textwrap


@dataclass(frozen=True)
class SandboxConfig:
    mode: str = "off"
    backend: str = "native"


class SandboxRunner:
    def __init__(self, config=None):
        self.config = config or SandboxConfig()

    def run(self, agent, command, timeout, runner):
        mode = str(self.config.mode or "off").strip()
        if mode == "off":
            return None
        if mode == "read_only":
            raise RuntimeError("sandbox read_only blocks run_shell")
        if mode != "best_effort":
            raise RuntimeError(f"unsupported sandbox mode: {mode}")
        return runner(command, timeout)


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
