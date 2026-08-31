"""Provider 瞬时故障归一化：适配层抛 ProviderError，engine 按 retryable 分流。

此前四个适配层全部 raise 裸 RuntimeError，ProviderError 在生产代码中没有任何
raise 点，should_retry_model_error 对生产路径的瞬时故障永远不重试（finding:
provider-recovery-unwired）——一次网络抖动即把长任务终结为不可恢复终态。
"""

import io
import json
import urllib.error
from unittest.mock import patch

import pytest

from repo_harness import RepoHarness, SessionStore, WorkspaceContext
from repo_harness.models import (
    AnthropicCompatibleModelClient,
    ChatCompletionsCompatibleModelClient,
    OllamaModelClient,
    OpenAICompatibleModelClient,
)
from repo_harness.providers.errors import ProviderError


def _http_error(code):
    return urllib.error.HTTPError(
        "https://provider.test/v1", code, "err", {}, io.BytesIO(b"{}")
    )


def _complete_raising(client, side_effect, **call_kwargs):
    with patch("time.sleep"), patch(
        "urllib.request.urlopen", side_effect=side_effect
    ):
        return client.complete("hello", 64, **call_kwargs)


def _agent_with_client(tmp_path, client):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    return RepoHarness(
        model_client=client,
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".repo-harness" / "sessions"),
    )


def _session_events(agent):
    return [
        json.loads(line)
        for line in agent.session_event_bus.path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class _FlakyModelClient:
    """先按顺序抛出注入的异常，再吐出脚本输出的模型 client。"""

    model = "fake"
    supports_prompt_cache = False

    def __init__(self, errors, outputs):
        self.errors = list(errors)
        self.outputs = list(outputs)
        self.last_completion_metadata = {}

    def complete(self, prompt, max_new_tokens, **kwargs):
        if self.errors:
            raise self.errors.pop(0)
        if not self.outputs:
            raise RuntimeError("fake model ran out of outputs")
        return self.outputs.pop(0)


def _transient_error():
    return ProviderError(
        "connection reset by peer",
        provider="openai-compatible",
        model="test-model",
        code="network_error",
        retryable=True,
        attempts=3,
        retry_count=2,
    )


# --- 适配层：瞬时故障抛 retryable ProviderError ---


def test_openai_adapter_connection_failure_is_retryable_provider_error():
    client = OpenAICompatibleModelClient("test-model", "https://api.test/v1", "key", None, 5)

    with pytest.raises(ProviderError) as excinfo:
        _complete_raising(client, urllib.error.URLError("timed out"))

    err = excinfo.value
    assert err.retryable is True
    assert err.code == "network_error"
    assert err.provider == "openai-compatible"
    assert err.model == "test-model"
    assert err.attempts == 3  # provider 层已重试 3 次
    assert err.retry_count == 2


def test_chat_completions_http_500_exhausts_retries_as_retryable_provider_error():
    client = ChatCompletionsCompatibleModelClient("test-model", "https://api.test/v1", "key", None, 5)

    with pytest.raises(ProviderError) as excinfo:
        _complete_raising(client, _http_error(500))

    err = excinfo.value
    assert err.retryable is True
    assert err.code == "http_500"
    assert err.http_status == 500
    assert err.attempts == 3
    assert err.retry_count == 2


def test_anthropic_http_400_is_not_retryable():
    client = AnthropicCompatibleModelClient("test-model", "https://api.test/v1", "key", None, 5)

    with pytest.raises(ProviderError) as excinfo:
        _complete_raising(client, _http_error(400))

    err = excinfo.value
    assert err.retryable is False
    assert err.code == "http_400"
    assert err.http_status == 400
    assert err.attempts == 1  # 4xx 不重试，第一抛即失败


def test_ollama_connection_failure_is_retryable_provider_error():
    client = OllamaModelClient("test-model", "http://localhost:11434", None, None, 5)

    with pytest.raises(ProviderError) as excinfo:
        _complete_raising(client, urllib.error.URLError("connection refused"))

    err = excinfo.value
    assert err.retryable is True
    assert err.code == "network_error"
    assert err.provider == "ollama"
    assert err.attempts == 1


def test_ollama_http_404_is_not_retryable():
    client = OllamaModelClient("test-model", "http://localhost:11434", None, None, 5)

    with pytest.raises(ProviderError) as excinfo:
        _complete_raising(client, _http_error(404))

    assert excinfo.value.retryable is False
    assert excinfo.value.http_status == 404


# --- engine 层：按 retryable 分流恢复或受控失败 ---


def test_transient_provider_error_is_retried_then_recovers(tmp_path):
    """瞬时网络错误：engine 重试一次后恢复，run 正常完成。"""
    client = _FlakyModelClient(
        [_transient_error()],
        ["<final>Recovered.</final>"],
    )
    agent = _agent_with_client(tmp_path, client)

    list(agent.engine.run_turn("do work"))

    assert agent.current_task_state.status == "completed"
    retries = [
        event
        for event in _session_events(agent)
        if event["event"] == "model_retry_scheduled" and event["code"] == "network_error"
    ]
    assert len(retries) == 1
    report = json.loads((agent.current_run_dir / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "completed"


def test_non_retryable_provider_error_finishes_as_failed_with_provider_metadata(tmp_path):
    """永久错误（HTTP 400）：受控失败路径，元数据保留 provider 语义。"""
    client = _FlakyModelClient(
        [
            ProviderError(
                "bad request",
                provider="openai-compatible",
                model="test-model",
                code="http_400",
                http_status=400,
                retryable=False,
            )
        ],
        ["<final>never reached</final>"],
    )
    agent = _agent_with_client(tmp_path, client)

    list(agent.engine.run_turn("do work"))

    assert agent.current_task_state.status == "failed"
    report = json.loads((agent.current_run_dir / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    error_meta = agent.last_completion_metadata["provider_error"]
    assert error_meta["code"] == "http_400"
    assert error_meta["provider"] == "openai-compatible"
    assert error_meta["http_status"] == 400
    assert not any(
        event["event"] == "model_retry_scheduled"
        for event in _session_events(agent)
    )


def test_retryable_provider_error_retries_once_per_code(tmp_path):
    """同一 code 的可重试错误只重试一次，重试后仍失败则受控终结。"""
    client = _FlakyModelClient([_transient_error(), _transient_error()], [])
    agent = _agent_with_client(tmp_path, client)

    list(agent.engine.run_turn("do work"))

    assert agent.current_task_state.status == "failed"
    retries = [
        event
        for event in _session_events(agent)
        if event["event"] == "model_retry_scheduled"
    ]
    assert len(retries) == 1
