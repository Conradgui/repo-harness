import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from repo_harness import WorkspaceContext
from repo_harness.config import resolve_runtime_config


def _args(tmp_path, **overrides):
    values = {
        "cwd": str(tmp_path),
        "provider": "openai",
        "_provider_explicit": False,
        "model": None,
        "_model_explicit": False,
        "base_url": None,
        "_base_url_explicit": False,
        "config": None,
        "max_steps": None,
        "_max_steps_explicit": False,
        "max_new_tokens": None,
        "_max_new_tokens_explicit": False,
        "sandbox": None,
        "sandbox_backend": None,
    }
    values.update(overrides)
    return type("Args", (), values)()


def test_runtime_config_merges_global_project_env_and_cli_precedence(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".repo-harness").mkdir()
    (home / ".repo-harness" / "config.toml").write_text(
        "\n".join(
            [
                'provider = "anthropic"',
                "max_steps = 9",
                "[providers.deepseek]",
                'client = "anthropic"',
                'model = "global-deepseek"',
                'base_url = "https://global.example/anthropic"',
                'api_key_env = "GLOBAL_DEEPSEEK_KEY"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / ".repo-harness.toml").write_text(
        "\n".join(
            [
                'provider = "deepseek"',
                "max_steps = 21",
                "max_new_tokens = 333",
                "[providers.deepseek]",
                'model = "project-deepseek"',
                'base_url = "https://project.example/anthropic"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        "REPO_HARNESS_MODEL=env-model\nREPO_HARNESS_MAX_NEW_TOKENS=444\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("REPO_HARNESS_MODEL", raising=False)
    monkeypatch.delenv("REPO_HARNESS_MAX_NEW_TOKENS", raising=False)

    config = resolve_runtime_config(_args(tmp_path), WorkspaceContext.build(tmp_path))
    cli_config = resolve_runtime_config(
        _args(tmp_path, model="cli-model", _model_explicit=True, max_steps=77, _max_steps_explicit=True),
        WorkspaceContext.build(tmp_path),
    )

    assert config.provider == "deepseek"
    assert config.provider_profile.client == "anthropic"
    assert config.provider_profile.model == "env-model"
    assert config.provider_profile.base_url == "https://project.example/anthropic"
    assert config.provider_profile.api_key_env == "GLOBAL_DEEPSEEK_KEY"
    assert config.max_steps == 21
    assert config.max_new_tokens == 444
    assert cli_config.provider_profile.model == "cli-model"
    assert cli_config.max_steps == 77


def test_public_cli_uses_mock_openai_provider_without_live_key(tmp_path):
    outputs = [
        '<tool>{"name":"write_file","args":{"path":"mock.txt","content":"mock provider\\n"}}</tool>',
        "<final>mock provider complete</final>",
    ]

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            text = outputs.pop(0)
            body = json.dumps({"output_text": text, "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        env = dict(os.environ)
        env["PYTHONPATH"] = os.getcwd() + os.pathsep + env.get("PYTHONPATH", "")
        env.pop("OPENAI_API_KEY", None)
        command = [
            sys.executable,
            "-m",
            "repo_harness",
            "--cwd",
            str(tmp_path),
            "--provider",
            "openai",
            "--base-url",
            f"http://127.0.0.1:{server.server_port}",
            "--model",
            "mock-model",
            "--approval",
            "auto",
            "run mock provider task",
        ]
        completed = subprocess.run(command, cwd=os.getcwd(), env=env, text=True, capture_output=True, timeout=60, check=False)
    finally:
        server.shutdown()
        server.server_close()

    assert completed.returncode == 0, completed.stderr
    assert "mock provider complete" in completed.stdout
    assert (tmp_path / "mock.txt").read_text(encoding="utf-8") == "mock provider\n"
