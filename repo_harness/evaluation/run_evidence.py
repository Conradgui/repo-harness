"""Structured run evidence for RepoHarness scenario gates."""

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ..models import FakeModelClient
from ..runtime import RepoHarness
from ..session_store import SessionStore
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
            self.run_public_cli_task_smoke(),
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

    def run_public_cli_task_smoke(self):
        workspace = self._prepare_workspace("public-cli-task-smoke")
        outputs = [
            '<tool>{"name":"write_file","args":{"path":"cli-task.txt","content":"RepoHarness CLI evidence\\n"}}</tool>',
            "<final>public cli task complete</final>",
        ]
        server = _MockOpenAIResponsesServer(outputs)
        server.start()
        try:
            command = [
                sys.executable,
                "-m",
                "repo_harness",
                "--cwd",
                str(workspace),
                "--provider",
                "openai",
                "--base-url",
                server.base_url,
                "--model",
                "evidence-model",
                "--approval",
                "auto",
                "create public CLI evidence",
            ]
            completed = subprocess.run(
                command,
                text=True,
                cwd=str(self.repo_root),
                env=self._subprocess_env(),
                capture_output=True,
                timeout=self.timeout,
                check=False,
            )
        finally:
            server.stop()
        stdout_path = self._write_log("public-cli-task-smoke.stdout.txt", completed.stdout)
        stderr_path = self._write_log("public-cli-task-smoke.stderr.txt", completed.stderr)
        changed_file = workspace / "cli-task.txt"
        report = _latest_file(workspace / ".repo-harness" / "runs", "report.json")
        trace = _latest_file(workspace / ".repo-harness" / "runs", "trace.jsonl")
        session_events = _latest_file(workspace / ".repo-harness" / "sessions", "*.events.jsonl")
        passed = (
            completed.returncode == 0
            and "public cli task complete" in completed.stdout
            and changed_file.is_file()
            and report.is_file()
            and trace.is_file()
            and session_events.is_file()
        )
        return ScenarioEvidence(
            id="public_cli_task_smoke",
            status="passed" if passed else "failed",
            driver="public_cli",
            workspace=str(workspace),
            detail="drove public CLI through a mocked provider tool-edit turn",
            artifacts={
                "stdout": str(stdout_path),
                "stderr": str(stderr_path),
                "changed_file": str(changed_file),
                "report": str(report),
                "trace": str(trace),
                "session_events": str(session_events),
                "state_dir": str(workspace / ".repo-harness"),
                "command": " ".join(command),
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
        env["NO_COLOR"] = "1"
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


def _latest_file(root, pattern):
    root = Path(root)
    if not root.exists():
        return Path("")
    files = sorted(root.rglob(pattern), key=lambda path: path.stat().st_mtime)
    return files[-1] if files else Path("")


class _MockOpenAIResponsesServer:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        parent = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                text = parent.outputs.pop(0) if parent.outputs else "<final>mock exhausted</final>"
                body = json.dumps(
                    {
                        "output_text": text,
                        "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
                    }
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.server.server_port}"

    def start(self):
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
