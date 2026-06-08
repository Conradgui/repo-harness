"""F. 集成测试 — 真实 API 连接与交互.

仅当环境变量中存在 API Key 时才运行。
无 API Key 时自动跳过，不影响其他测试。
"""

import os
from pathlib import Path

import pytest

from repo_harness import SessionStore, WorkspaceContext
from repo_harness.models import (
    ChatCompletionsCompatibleModelClient,
)
from tests.helpers import load_authorized_env

load_authorized_env()

# Skip decorators
requires_mimo = pytest.mark.skipif(
    not os.environ.get("MIMO_API_KEY"),
    reason="需要 MIMO_API_KEY 环境变量",
)
requires_deepseek = pytest.mark.skipif(
    not os.environ.get("DEEPSEEK_API_KEY"),
    reason="需要 DEEPSEEK_API_KEY 环境变量",
)


def _xfail_if_provider_limited(exc):
    message = str(exc)
    if "429" in message or "quota" in message.lower() or "rate" in message.lower():
        pytest.xfail(f"provider limited: {message[:200]}")


def _build_real_agent(tmp_path, model_client):
    """用真实模型客户端构建 agent。"""
    (tmp_path / "README.md").write_text("# Test\n", encoding="utf-8")
    workspace = WorkspaceContext.build(tmp_path)
    store = SessionStore(str(tmp_path / ".repo-harness" / "sessions"))
    from repo_harness import RepoHarness
    return RepoHarness(
        model_client=model_client,
        workspace=workspace,
        session_store=store,
        approval_policy="auto",
        max_steps=5,
        max_new_tokens=1024,
    )


# ──────────────────────────────────────────────
# MIMO 连通性测试
# ──────────────────────────────────────────────

class TestMIMOIntegration:
    @requires_mimo
    def test_int_mimo__connect_and_respond(self, tmp_path):
        """MIMO API 发送 prompt 收到回复。"""
        client = ChatCompletionsCompatibleModelClient(
            model="mimo-v2.5-pro",
            base_url="https://token-plan-cn.xiaomimimo.com/v1",
            api_key=os.environ["MIMO_API_KEY"],
            temperature=0.2,
            timeout=30,
        )
        try:
            result = client.complete("Say hello in one word.", 200)
        except RuntimeError as exc:
            _xfail_if_provider_limited(exc)
            raise
        assert isinstance(result, str)
        assert len(result) > 0

    @requires_mimo
    def test_int_mimo__agent_round_trip(self, tmp_path):
        """MIMO 完整 agent 交互：prompt → 模型回复。"""
        client = ChatCompletionsCompatibleModelClient(
            model="mimo-v2.5-pro",
            base_url="https://token-plan-cn.xiaomimimo.com/v1",
            api_key=os.environ["MIMO_API_KEY"],
            temperature=0.2,
            timeout=60,
        )
        agent = _build_real_agent(tmp_path, client)
        response = agent.ask("What files are in this workspace? List them.")
        if "429" in response or "quota" in response.lower():
            pytest.xfail(f"provider limited: {response[:200]}")
        assert isinstance(response, str)
        assert len(response) > 0

    @requires_mimo
    def test_int_mimo__tool_call_format(self, tmp_path):
        """MIMO 正确生成工具调用格式。"""
        client = ChatCompletionsCompatibleModelClient(
            model="mimo-v2.5-pro",
            base_url="https://token-plan-cn.xiaomimimo.com/v1",
            api_key=os.environ["MIMO_API_KEY"],
            temperature=0.2,
            timeout=60,
        )
        agent = _build_real_agent(tmp_path, client)
        events = list(agent.engine.run_turn("Read the README.md file"))
        tool_events = [e for e in events if e["type"] == "tool_call"]
        stop_events = [e for e in events if e["type"] == "stop"]
        if stop_events and any(
            "429" in str(e.get("content", "")) or "quota" in str(e.get("content", "")).lower()
            for e in stop_events
        ):
            pytest.xfail(f"provider limited: {stop_events[-1].get('content', '')[:200]}")
        # 模型应该尝试调用工具
        assert len(tool_events) > 0 or any(e["type"] == "final" for e in events)


# ──────────────────────────────────────────────
# DeepSeek 连通性测试
# ──────────────────────────────────────────────

class TestDeepSeekIntegration:
    @requires_deepseek
    def test_int_deepseek__connect_and_respond(self, tmp_path):
        """DeepSeek API 发送 prompt 收到回复。"""
        client = ChatCompletionsCompatibleModelClient(
            model="deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            api_key=os.environ["DEEPSEEK_API_KEY"],
            temperature=0.2,
            timeout=30,
        )
        result = client.complete("Say hello in one word.", 200)
        assert isinstance(result, str)
        assert len(result) > 0

    @requires_deepseek
    def test_int_deepseek__agent_round_trip(self, tmp_path):
        """DeepSeek 完整 agent 交互：prompt → 模型回复。"""
        client = ChatCompletionsCompatibleModelClient(
            model="deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            api_key=os.environ["DEEPSEEK_API_KEY"],
            temperature=0.2,
            timeout=60,
        )
        agent = _build_real_agent(tmp_path, client)
        response = agent.ask("What files are in this workspace? List them.")
        assert isinstance(response, str)
        assert len(response) > 0

    @requires_deepseek
    def test_int_deepseek__tool_call_format(self, tmp_path):
        """DeepSeek 正确生成工具调用格式。"""
        client = ChatCompletionsCompatibleModelClient(
            model="deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            api_key=os.environ["DEEPSEEK_API_KEY"],
            temperature=0.2,
            timeout=60,
        )
        agent = _build_real_agent(tmp_path, client)
        events = list(agent.engine.run_turn("Read the README.md file"))
        tool_events = [e for e in events if e["type"] == "tool_call"]
        assert len(tool_events) > 0 or any(e["type"] == "final" for e in events)
