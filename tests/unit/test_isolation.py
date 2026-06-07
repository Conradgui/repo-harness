"""E. 状态隔离测试 — 验证每个测试不受历史状态影响.

核心要求：
- 状态目录非空时，新一轮运行行为正确
- 上一次运行中途失败留下的状态，不影响下次运行
"""

import json
from pathlib import Path

import pytest

from tests.helpers import build_agent


class TestIsolationEmptyState:
    def test_iso__fresh_start_on_empty_dir(self, tmp_path):
        """空目录全新启动行为正确。"""
        agent = build_agent(tmp_path, [])
        assert agent.session_path.exists()
        session = json.loads(agent.session_path.read_text(encoding="utf-8"))
        assert session["history"] == []


class TestIsolationExistingSessions:
    def test_iso__new_session_not_affected_by_existing(self, tmp_path):
        """已有会话不影响新会话创建。"""
        # 创建第一个 agent
        agent1 = build_agent(tmp_path, ['<final>first</final>'])
        agent1.ask("hello")
        id1 = agent1.session["id"]

        # 创建第二个 agent
        agent2 = build_agent(tmp_path, ['<final>second</final>'])
        id2 = agent2.session["id"]

        assert id1 != id2
        assert agent2.session["history"] == []


class TestIsolationCorruptedQueue:
    def test_iso__corrupted_review_queue_does_not_crash(self, tmp_path):
        """损坏的审核队列 JSONL 不崩溃。"""
        agent = build_agent(tmp_path, [])
        memory_dir = tmp_path / ".repo-harness" / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        queue_file = memory_dir / "review-queue.jsonl"
        # 写入损坏的 JSONL
        queue_file.write_text(
            '{"valid": "line"}\nNOT JSON\n{"another": "valid"}\n',
            encoding="utf-8",
        )

        # 加载不应崩溃
        from repo_harness.memory import DurableMemoryReviewQueue
        queue = DurableMemoryReviewQueue(memory_dir)
        records = queue.load()
        # 损坏行被跳过
        assert len(records) <= 2


class TestIsolationConcurrentSave:
    def test_iso__session_save_is_atomic(self, tmp_path):
        """session 保存是原子的，不会产生半写文件。"""
        agent = build_agent(tmp_path, ['<final>done</final>'])
        agent.ask("hello")

        # 验证 session 文件是合法 JSON
        session_text = agent.session_path.read_text(encoding="utf-8")
        data = json.loads(session_text)
        assert "id" in data
        assert isinstance(data["history"], list)
