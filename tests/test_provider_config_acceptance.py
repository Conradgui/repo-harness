import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from repo_harness import WorkspaceContext
from repo_harness.config import resolve_runtime_config
from repo_harness.provider_registry import PROVIDER_REGISTRY, provider_names
from repo_harness.provider_setup import (
    ProviderDoctorResult,
    build_provider_setup_toml,
    classify_provider_error,
    detect_provider_from_base_url,
    probe_provider_endpoint,
    provider_doctor,
    write_provider_config,
)


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


def _init_workspace_repo(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return tmp_path


class _ProbeServer:
    def __init__(self, responses):
        self.responses = responses
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8")
                outer.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
                status, payload = outer.responses.get(self.path, (404, {"error": "not found"}))
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *_args):
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_exc):
        self.server.shutdown()
        self.server.server_close()

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.server.server_port}/v1"


def test_runtime_config_merges_global_project_env_and_cli_precedence(tmp_path, monkeypatch):
    _init_workspace_repo(tmp_path)
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
    _init_workspace_repo(tmp_path)
    outputs = [
        '<tool>{"name":"write_file","args":{"path":"mock.txt","content":"mock provider\\n"}}</tool>',
        '<tool>{"name":"run_shell","args":{"command":"python -m pytest --version","timeout":60}}</tool>',
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
        completed = subprocess.run(command, cwd=os.getcwd(), env=env, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=60, check=False)
    finally:
        server.shutdown()
        server.server_close()

    assert completed.returncode == 0, completed.stderr
    assert "mock provider complete" in completed.stdout
    assert (tmp_path / "mock.txt").read_text(encoding="utf-8") == "mock provider\n"


def test_provider_setup_detects_chat_completions_and_writes_env_name_only():
    provider = detect_provider_from_base_url("https://models.example.com/v1/chat/completions")
    rendered = build_provider_setup_toml(
        provider=provider,
        model="vendor-model",
        base_url="https://models.example.com/v1/chat/completions",
        api_key_env="VENDOR_API_KEY",
    )

    assert provider == "chat-completions"
    assert 'provider = "chat-completions"' in rendered
    assert 'base_url = "https://models.example.com/v1"' in rendered
    assert 'api_key_env = "VENDOR_API_KEY"' in rendered
    assert "secret" not in rendered.lower()


def test_provider_setup_requires_provider_for_ambiguous_version_root(tmp_path):
    _init_workspace_repo(tmp_path)
    env = dict(os.environ)
    env["PYTHONPATH"] = os.getcwd() + os.pathsep + env.get("PYTHONPATH", "")

    setup = subprocess.run(
        [
            sys.executable,
            "-m",
            "repo_harness",
            "provider",
            "setup",
            "--base-url",
            "https://models.example.com/v1",
            "--model",
            "vendor-model",
            "--api-key-env",
            "VENDOR_API_KEY",
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert setup.returncode == 2
    assert "could not infer provider" in setup.stderr
    assert not (tmp_path / ".repo-harness.toml").exists()


def test_provider_setup_uses_known_root_host_hints():
    assert detect_provider_from_base_url("https://api.openai.com/v1") == "openai"
    assert detect_provider_from_base_url("https://api.anthropic.com/v1") == "anthropic"
    assert detect_provider_from_base_url("https://api.deepseek.com/anthropic") == "deepseek"
    assert detect_provider_from_base_url("https://api.deepseek.com/anthropic/messages") == "deepseek"
    assert detect_provider_from_base_url("https://token-plan-cn.xiaomimimo.com/v1") == "chat-completions"


def test_provider_setup_rejects_base_url_with_credentials_query_or_fragment():
    with pytest.raises(ValueError, match="base_url must not include"):
        build_provider_setup_toml(
            provider="chat-completions",
            model="vendor-model",
            base_url="https://user:sk-secret@models.example.com/v1?api_key=sk-secret#token",
            api_key_env="VENDOR_API_KEY",
        )


def test_provider_setup_rejects_token_shaped_env_name_even_when_syntax_valid():
    with pytest.raises(ValueError, match="environment variable name"):
        build_provider_setup_toml(
            provider="chat-completions",
            model="vendor-model",
            base_url="https://models.example.com/v1/chat/completions",
            api_key_env="ghp_abcdefghijklmnopqrstuvwxyz123456",
        )


def test_provider_registry_lists_supported_providers_as_single_source_of_truth():
    assert set(provider_names()) == {"ollama", "openai", "chat-completions", "anthropic", "deepseek"}
    assert PROVIDER_REGISTRY["chat-completions"].endpoint_path == "/chat/completions"
    assert PROVIDER_REGISTRY["openai"].endpoint_path == "/responses"
    assert PROVIDER_REGISTRY["deepseek"].client == "anthropic"


def test_provider_probe_default_does_not_send_live_requests():
    with _ProbeServer(
        {
            "/v1/chat/completions": (
                200,
                {"choices": [{"message": {"content": "ok"}}], "usage": {"prompt_tokens": 1, "completion_tokens": 1}},
            )
        }
    ) as server:
        result = probe_provider_endpoint(
            base_url=server.base_url + "/chat/completions",
            model="vendor-model",
            api_key_env="VENDOR_API_KEY",
            environment={"VENDOR_API_KEY": "secret-token-value"},
        )

    assert result.ok is True
    assert result.provider == "chat-completions"
    assert result.base_url == server.base_url
    assert server.requests == []
    assert "secret-token-value" not in result.render()


def test_provider_probe_smoke_recommends_openai_responses_endpoint():
    with _ProbeServer({"/v1/responses": (200, {"output_text": "ok", "usage": {"input_tokens": 1, "output_tokens": 1}})}) as server:
        result = probe_provider_endpoint(
            base_url=server.base_url,
            model="vendor-model",
            api_key_env="VENDOR_API_KEY",
            environment={"VENDOR_API_KEY": "secret-token-value"},
            smoke=True,
        )

    assert result.ok is True
    assert result.provider == "openai"


def test_provider_probe_stops_on_unauthorized_without_trying_to_guess_protocol():
    with _ProbeServer({"/v1/responses": (401, {"error": {"message": "Invalid API Key sk-secret-value"}})}) as server:
        result = probe_provider_endpoint(
            base_url=server.base_url,
            model="vendor-model",
            api_key_env="VENDOR_API_KEY",
            environment={"VENDOR_API_KEY": "secret-token-value"},
            smoke=True,
        )

    assert result.ok is False
    assert result.provider == ""
    assert "key" in result.summary.lower()
    assert "openai" in result.summary.lower()
    assert "sk-secret-value" not in result.render()
    assert "/v1/chat/completions" not in [item["path"] for item in server.requests]


def test_provider_cli_probe_write_updates_config_with_detected_provider(tmp_path):
    _init_workspace_repo(tmp_path)
    env = dict(os.environ)
    env["PYTHONPATH"] = os.getcwd() + os.pathsep + env.get("PYTHONPATH", "")
    env["VENDOR_API_KEY"] = "secret-token-value"
    with _ProbeServer(
        {
            "/v1/chat/completions": (
                200,
                {"choices": [{"message": {"content": "ok"}}], "usage": {"prompt_tokens": 1, "completion_tokens": 1}},
            )
        }
    ) as server:
        probe = subprocess.run(
            [
                sys.executable,
                "-m",
                "repo_harness",
                "provider",
                "probe",
                "--base-url",
                server.base_url + "/chat/completions",
                "--model",
                "vendor-model",
                "--api-key-env",
                "VENDOR_API_KEY",
                "--write",
            ],
            cwd=tmp_path,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=30,
            check=False,
        )

    assert probe.returncode == 0, probe.stderr
    assert "recommended provider: chat-completions" in probe.stdout
    text = (tmp_path / ".repo-harness.toml").read_text(encoding="utf-8")
    assert 'provider = "chat-completions"' in text
    assert 'model = "vendor-model"' in text
    assert 'api_key_env = "VENDOR_API_KEY"' in text
    assert "secret-token-value" not in text


def test_provider_cli_probe_rejects_secret_like_api_key_env(tmp_path):
    _init_workspace_repo(tmp_path)
    env = dict(os.environ)
    env["PYTHONPATH"] = os.getcwd() + os.pathsep + env.get("PYTHONPATH", "")

    probe = subprocess.run(
        [
            sys.executable,
            "-m",
            "repo_harness",
            "provider",
            "probe",
            "--base-url",
            "https://models.example.com/v1/chat/completions",
            "--model",
            "vendor-model",
            "--api-key-env",
            "sk-secret-value",
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert probe.returncode == 2
    assert "environment variable name" in probe.stderr
    assert "sk-secret-value" not in probe.stdout
    assert "sk-secret-value" not in probe.stderr


def test_provider_setup_rejects_unsupported_provider_names():
    with pytest.raises(ValueError, match="provider must be one of"):
        build_provider_setup_toml(
            provider='chat-completions]\n[providers.evil',
            model="vendor-model",
            base_url="https://models.example.com/v1/chat/completions",
            api_key_env="VENDOR_API_KEY",
        )


def test_provider_setup_merges_existing_config_without_dropping_unrelated_sections(tmp_path):
    _init_workspace_repo(tmp_path)
    config_path = tmp_path / ".repo-harness.toml"
    config_path.write_text(
        "\n".join(
            [
                "# user-owned RepoHarness settings",
                'provider = "openai"',
                "max_steps = 21",
                "",
                "[sandbox]",
                'mode = "best_effort"',
                'backend = "native"',
                "",
                "[providers.openai]",
                'model = "existing-openai"',
                'base_url = "https://openai.example/v1"',
                'api_key_env = "OPENAI_API_KEY"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    written = write_provider_config(
        workspace_root=tmp_path,
        provider="chat-completions",
        model="vendor-model",
        base_url="https://models.example.com/v1/chat/completions",
        api_key_env="VENDOR_API_KEY",
    )

    assert written == config_path
    text = config_path.read_text(encoding="utf-8")
    assert "# user-owned RepoHarness settings" in text
    assert 'provider = "chat-completions"' in text
    assert "max_steps = 21" in text
    assert "[sandbox]" in text
    assert 'mode = "best_effort"' in text
    assert "[providers.openai]" in text
    assert 'model = "existing-openai"' in text
    assert "[providers.chat-completions]" in text
    assert 'model = "vendor-model"' in text
    assert 'base_url = "https://models.example.com/v1"' in text
    assert 'api_key_env = "VENDOR_API_KEY"' in text


def test_provider_setup_replaces_existing_target_provider_section_once(tmp_path):
    _init_workspace_repo(tmp_path)
    config_path = tmp_path / ".repo-harness.toml"
    config_path.write_text(
        "\n".join(
            [
                'provider = "chat-completions"',
                "",
                "[providers.chat-completions]",
                'client = "chat-completions"',
                'model = "old-model"',
                'base_url = "https://old.example/v1"',
                'api_key_env = "OLD_KEY"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    write_provider_config(
        workspace_root=tmp_path,
        provider="chat-completions",
        model="new-model",
        base_url="https://new.example/v1/chat/completions",
        api_key_env="NEW_KEY",
    )

    text = config_path.read_text(encoding="utf-8")
    assert text.count("[providers.chat-completions]") == 1
    assert 'model = "new-model"' in text
    assert 'base_url = "https://new.example/v1"' in text
    assert 'api_key_env = "NEW_KEY"' in text
    assert "old-model" not in text


def test_provider_setup_updates_target_provider_keys_without_dropping_section_notes(tmp_path):
    _init_workspace_repo(tmp_path)
    config_path = tmp_path / ".repo-harness.toml"
    config_path.write_text(
        "\n".join(
            [
                'provider = "chat-completions"',
                "",
                "[providers.chat-completions]",
                "# keep this provider note",
                'client = "chat-completions"',
                'model = "old-model"',
                'custom_option = "preserve-me"',
                "",
                "# keep this lower note",
                'base_url = "https://old.example/v1"',
                'api_key_env = "OLD_KEY"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    write_provider_config(
        workspace_root=tmp_path,
        provider="chat-completions",
        model="new-model",
        base_url="https://new.example/v1/chat/completions",
        api_key_env="NEW_KEY",
    )

    text = config_path.read_text(encoding="utf-8")
    assert "# keep this provider note" in text
    assert "# keep this lower note" in text
    assert 'custom_option = "preserve-me"' in text
    assert 'model = "new-model"' in text
    assert 'base_url = "https://new.example/v1"' in text
    assert 'api_key_env = "NEW_KEY"' in text


def test_provider_setup_updates_section_with_inline_comment_header_without_duplicate_table(tmp_path):
    _init_workspace_repo(tmp_path)
    config_path = tmp_path / ".repo-harness.toml"
    config_path.write_text(
        "\n".join(
            [
                'provider = "chat-completions"',
                "",
                "[providers.chat-completions] # primary model",
                'client = "chat-completions"',
                'model = "old-model"',
                'base_url = "https://old.example/v1"',
                'api_key_env = "OLD_KEY"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    write_provider_config(
        workspace_root=tmp_path,
        provider="chat-completions",
        model="new-model",
        base_url="https://new.example/v1/chat/completions",
        api_key_env="NEW_KEY",
    )

    text = config_path.read_text(encoding="utf-8")
    assert text.count("[providers.chat-completions]") == 1
    assert "[providers.chat-completions] # primary model" in text
    assert 'model = "new-model"' in text
    assert 'base_url = "https://new.example/v1"' in text
    assert 'api_key_env = "NEW_KEY"' in text


def test_provider_doctor_reports_missing_key_without_leaking_configured_secret(tmp_path, monkeypatch):
    _init_workspace_repo(tmp_path)
    (tmp_path / ".repo-harness.toml").write_text(
        "\n".join(
            [
                'provider = "chat-completions"',
                "[providers.chat-completions]",
                'model = "vendor-model"',
                'base_url = "https://models.example.com/v1"',
                'api_key_env = "VENDOR_API_KEY"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("VENDOR_API_KEY", raising=False)

    result = provider_doctor(workspace_root=tmp_path, smoke=False)

    assert result.ok is False
    assert result.provider == "chat-completions"
    assert result.api_key_env == "VENDOR_API_KEY"
    assert "missing" in result.summary.lower()
    assert "VENDOR_API_KEY" in result.render()
    assert "Bearer" not in result.render()


def test_provider_error_classifier_explains_common_setup_failures():
    assert "key" in classify_provider_error("HTTP 401 invalid api key").lower()
    assert "provider" in classify_provider_error("HTTP 404 not found").lower()
    assert "rate" in classify_provider_error("HTTP 429 too many requests").lower()


def test_provider_cli_setup_and_doctor_do_not_write_secret_values(tmp_path):
    _init_workspace_repo(tmp_path)
    env = dict(os.environ)
    env["PYTHONPATH"] = os.getcwd() + os.pathsep + env.get("PYTHONPATH", "")
    secret_value = "secret-token-value-that-must-not-be-written"
    env["VENDOR_API_KEY"] = secret_value

    setup = subprocess.run(
        [
            sys.executable,
            "-m",
            "repo_harness",
            "provider",
            "setup",
            "--base-url",
            "https://models.example.com/v1/chat/completions",
            "--model",
            "vendor-model",
            "--api-key-env",
            "VENDOR_API_KEY",
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert setup.returncode == 0, setup.stderr
    config_text = (tmp_path / ".repo-harness.toml").read_text(encoding="utf-8")
    assert "VENDOR_API_KEY" in config_text
    assert secret_value not in config_text

    doctor = subprocess.run(
        [sys.executable, "-m", "repo_harness", "provider", "doctor"],
        cwd=tmp_path,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert doctor.returncode == 0, doctor.stderr
    assert "provider: chat-completions" in doctor.stdout
    assert "key present: yes" in doctor.stdout
    assert secret_value not in doctor.stdout


def test_provider_cli_setup_from_subdirectory_writes_repo_root_config(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    subdir = tmp_path / "nested"
    subdir.mkdir()
    env = dict(os.environ)
    env["PYTHONPATH"] = os.getcwd() + os.pathsep + env.get("PYTHONPATH", "")

    setup = subprocess.run(
        [
            sys.executable,
            "-m",
            "repo_harness",
            "provider",
            "setup",
            "--base-url",
            "https://models.example.com/v1/chat/completions",
            "--model",
            "vendor-model",
            "--api-key-env",
            "VENDOR_API_KEY",
        ],
        cwd=subdir,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert setup.returncode == 0, setup.stderr
    assert (tmp_path / ".repo-harness.toml").is_file()
    assert not (subdir / ".repo-harness.toml").exists()


def test_provider_setup_rejects_secret_like_api_key_env(tmp_path):
    _init_workspace_repo(tmp_path)
    env = dict(os.environ)
    env["PYTHONPATH"] = os.getcwd() + os.pathsep + env.get("PYTHONPATH", "")

    setup = subprocess.run(
        [
            sys.executable,
            "-m",
            "repo_harness",
            "provider",
            "setup",
            "--base-url",
            "https://models.example.com/v1/chat/completions",
            "--model",
            "vendor-model",
            "--api-key-env",
            "sk-secret-value",
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert setup.returncode == 2
    assert not (tmp_path / ".repo-harness.toml").exists()
    assert "environment variable name" in setup.stderr


def test_provider_doctor_render_redacts_detail_secret():
    result = ProviderDoctorResult(
        ok=False,
        provider="chat-completions",
        model="vendor-model",
        base_url="https://models.example.com/v1",
        api_key_env="VENDOR_API_KEY",
        key_present=True,
        summary="failed",
        detail="HTTP 401 Authorization: Bearer sk-secret-value OPENAI_API_KEY=sk-other-secret",
    )

    rendered = result.render()

    assert "sk-secret-value" not in rendered
    assert "sk-other-secret" not in rendered
    assert "<redacted>" in rendered


def test_provider_result_render_redacts_secret_shaped_fields():
    result = ProviderDoctorResult(
        ok=False,
        provider="chat-completions",
        model="sk-model-secret",
        base_url="https://models.example.com/v1?api_key=sk-url-secret",
        api_key_env="sk-secret-value",
        key_present=True,
        summary="failed with token=sk-summary-secret",
        detail="Authorization: Bearer sk-detail-secret",
    )

    rendered = result.render()

    assert "sk-model-secret" not in rendered
    assert "sk-url-secret" not in rendered
    assert "sk-secret-value" not in rendered
    assert "sk-summary-secret" not in rendered
    assert "sk-detail-secret" not in rendered
    assert "<redacted>" in rendered


def test_runtime_config_rejects_unknown_provider(tmp_path):
    _init_workspace_repo(tmp_path)
    (tmp_path / ".repo-harness.toml").write_text(
        'provider = "unknown-provider"\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="provider must be one of"):
        resolve_runtime_config(_args(tmp_path), WorkspaceContext.build(tmp_path))
