"""Structured run evidence for RepoHarness scenario gates."""

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from ..models import FakeModelClient
from ..runtime import RepoHarness, SessionStore
from ..workspace import WorkspaceContext, now


@dataclass(frozen=True)
class ScenarioEvidence:
    id: str
    status: str
    driver: str
    workspace: str
    detail: str
    artifacts: dict
    checked_at: str
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""

    def to_dict(self):
        return asdict(self)


class RunEvidence:
    """Collects evidence through the same public and runtime surfaces users call."""

    def __init__(self, output_dir, repo_root=None, timeout=30):
        self.output_dir = Path(output_dir)
        self.repo_root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
        self.timeout = int(timeout)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir = self.output_dir / "logs"
        self.workspaces_dir = self.output_dir / "workspaces"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.workspaces_dir.mkdir(parents=True, exist_ok=True)

    def run(self):
        scenarios = [
            self.run_public_cli_smoke(),
            self.run_scripted_runtime_smoke(),
        ]
        status = "passed" if all(item["status"] == "passed" for item in scenarios) else "failed"
        payload = {
            "schema_version": "repo-harness-run-evidence-v1",
            "status": status,
            "scenario_count": len(scenarios),
            "scenarios": scenarios,
            "output_dir": str(self.output_dir),
            "logs_dir": str(self.logs_dir),
            "workspaces_dir": str(self.workspaces_dir),
            "state_dir": ".repo-harness",
            "generated_at": now(),
        }
        self._write_json("run-evidence.json", payload)
        self._write_summary(payload)
        return payload

    def run_public_cli_smoke(self):
        workspace = self._prepare_workspace("public-cli-smoke")
        command = [
            sys.executable,
            "-m",
            "repo_harness",
            "--cwd",
            str(workspace),
            "--approval",
            "auto",
            "--repl",
        ]
        env = self._subprocess_env()
        completed = subprocess.run(
            command,
            input="/help\n/exit\n",
            text=True,
            cwd=str(self.repo_root),
            env=env,
            capture_output=True,
            timeout=self.timeout,
            check=False,
        )
        stdout_path = self._write_log("public-cli-smoke.stdout.txt", completed.stdout)
        stderr_path = self._write_log("public-cli-smoke.stderr.txt", completed.stderr)
        passed = completed.returncode == 0 and "RepoHarness" in completed.stdout and "Commands:" in completed.stdout
        return ScenarioEvidence(
            id="public_cli_smoke",
            status="passed" if passed else "failed",
            driver="public_cli",
            workspace=str(workspace),
            detail="drove repo_harness public CLI through stdin commands",
            artifacts={
                "stdout": str(stdout_path),
                "stderr": str(stderr_path),
                "command": " ".join(command),
                "state_dir": str(workspace / ".repo-harness"),
            },
            checked_at=now(),
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        ).to_dict()

    def run_scripted_runtime_smoke(self):
        workspace = self._prepare_workspace("scripted-runtime-smoke")
        agent = RepoHarness(
            model_client=FakeModelClient(
                [
                    '<tool>{"name":"write_file","args":{"path":"src/result.txt","content":"RepoHarness scripted evidence\\n"}}</tool>',
                    "<final>scripted evidence complete</final>",
                ]
            ),
            workspace=WorkspaceContext.build(workspace),
            session_store=SessionStore(workspace / ".repo-harness" / "sessions"),
            approval_policy="auto",
        )
        answer = agent.ask("create scripted evidence")
        output_path = workspace / "src" / "result.txt"
        passed = answer == "scripted evidence complete" and output_path.is_file()
        artifacts = {
            "result": str(output_path),
            "run_dir": str(agent.current_run_dir),
            "report": str(agent.current_run_dir / "report.json"),
            "trace": str(agent.current_run_dir / "trace.jsonl"),
            "session_events": str(agent.session_event_bus.path),
            "state_dir": str(workspace / ".repo-harness"),
        }
        return ScenarioEvidence(
            id="scripted_runtime_smoke",
            status="passed" if passed else "failed",
            driver="fake_provider",
            workspace=str(workspace),
            detail=answer,
            artifacts=artifacts,
            checked_at=now(),
        ).to_dict()

    def _prepare_workspace(self, name):
        workspace = self.workspaces_dir / name
        workspace.mkdir(parents=True, exist_ok=True)
        readme = workspace / "README.md"
        if not readme.exists():
            readme.write_text("RepoHarness evidence workspace\n", encoding="utf-8")
        return workspace

    def _subprocess_env(self):
        env = dict(os.environ)
        existing = env.get("PYTHONPATH", "")
        parts = [str(self.repo_root)]
        if existing:
            parts.append(existing)
        env["PYTHONPATH"] = os.pathsep.join(parts)
        return env

    def _write_log(self, name, content):
        path = self.logs_dir / name
        path.write_text(str(content), encoding="utf-8")
        return path

    def _write_json(self, name, payload):
        path = self.output_dir / name
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def _write_summary(self, payload):
        lines = [
            "# RepoHarness Run Evidence",
            "",
            f"status: {payload['status']}",
            f"state_dir: {payload['state_dir']}",
            "",
        ]
        for scenario in payload["scenarios"]:
            lines.append(f"- {scenario['id']}: {scenario['status']} ({scenario['driver']})")
        (self.output_dir / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(output_dir):
    return RunEvidence(Path(output_dir)).run()


def run_isolated(output_dir=None):
    root = Path(output_dir) if output_dir is not None else Path(tempfile.mkdtemp(prefix="repo-harness-run-evidence-"))
    return RunEvidence(root).run()
