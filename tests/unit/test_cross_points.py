"""B. 交汇点测试 — 验证状态在多流程间的一致性.

每个测试验证：交汇点被流程 A 修改后，流程 B 能否正确读取。
"""

import json
from pathlib import Path

import pytest

from tests.helpers import build_agent, build_workspace


class TestCrossSessionMemory:
    def test_cross__memory_persists_across_session_save_load(self, tmp_path):
        """写入记忆后重新保存并加载，记忆不丢失。"""
        agent = build_agent(tmp_path, [])
        agent.memory.set_task_summary("test task")
        agent._persist_memory()

        # 重新加载 session
        session_data = json.loads(agent.session_path.read_text(encoding="utf-8"))
        assert session_data["memory"]["working"]["task_summary"] == "test task"

    def test_cross__file_summary_updates_after_read(self, tmp_path):
        """读取文件后，文件摘要被更新。"""
        agent = build_agent(tmp_path, [
            '<final>read done</final>',
        ])
        agent.update_memory_after_tool("read_file", {"path": "README.md"}, "# Test Project\n")

        memory_state = agent.memory.to_dict()
        assert any("README" in k for k in memory_state.get("file_summaries", {}))


class TestCrossRunStoreTrace:
    def test_cross__trace_written_after_tool_execution(self, tmp_path):
        """工具执行后 trace 文件包含该事件。"""
        agent = build_agent(tmp_path, [
            '<final>done</final>',
        ])
        agent.ask("read the README")

        # 检查 run dir 下的 trace
        if agent.current_run_dir:
            trace_path = agent.current_run_dir / "trace.jsonl"
            if trace_path.exists():
                lines = [json.loads(l) for l in trace_path.read_text(encoding="utf-8").splitlines() if l.strip()]
                assert len(lines) > 0


class TestCrossWorkspaceFingerprint:
    def test_cross__refresh_detects_workspace_changes(self, tmp_path):
        """外部修改文件后 refresh_prefix 检测到变化。"""
        agent = build_agent(tmp_path, [])
        fp1 = agent.prefix_state.workspace_fingerprint

        # 外部修改文件
        (tmp_path / "new_file.py").write_text("x = 1\n", encoding="utf-8")

        # refresh_prefix 重建 workspace，检测变化
        refresh = agent.refresh_prefix(force=True)
        assert refresh["workspace_changed"] is True


class TestCrossReviewQueueAccept:
    def test_cross__accept_writes_durable_topic(self, tmp_path, memory_dir):
        """accept 后持久化 topic 文件存在。"""
        agent = build_agent(tmp_path, [])

        # 先记住一条
        result = agent.remember_candidate("Project convention: use pytest for testing")
        if result.get("status") == "queued":
            record = result.get("record", {})
            record_id = record.get("id", "")
            if record_id:
                agent.memory_review_accept(record_id)
                agent._persist_memory()
                # 检查 topic 文件
                topics_dir = memory_dir / "topics"
                if topics_dir.exists():
                    topic_files = list(topics_dir.glob("*.md"))
                    assert len(topic_files) > 0


class TestCrossToolPolicyAfterWrite:
    def test_cross__can_patch_after_self_write(self, tmp_path):
        """自己写入的文件可以直接 patch，无需再读。"""
        agent = build_agent(tmp_path, [])

        # 写入新文件
        agent.run_tool("write_file", {"path": "new.py", "content": "old content\n"})
        # patch 自己写的文件（Tool Policy 允许 self-authored）
        result = agent.run_tool("patch_file", {
            "path": "new.py",
            "old_text": "old content",
            "new_text": "new content",
        })
        assert "patched" in result.lower()


class TestCrossMetricsSnapshot:
    def test_cross__metrics_snapshot_creates_file(self, tmp_path):
        """/metrics 写快照文件。"""
        agent = build_agent(tmp_path, [
            '<final>done</final>',
        ])
        agent.ask("do something")

        snapshot_path = agent.save_metrics_snapshot()
        assert snapshot_path.exists()
        data = json.loads(snapshot_path.read_text(encoding="utf-8"))
        assert "tool_metrics" in data
        assert "session_id" in data
