"""D. 错误传播测试 — 在关键节点注入错误，验证错误被正确传播.

核心要求：
- 系统在正确的地方报错，不静默失败
- 错误信息对用户有帮助
"""

import sys

import pytest

from tests.helpers import build_agent


class TestErrorModelTimeout:
    def test_err__model_timeout_returns_helpful_message(self, tmp_path):
        """模型超时后返回有用错误信息。"""
        from repo_harness.models import FakeModelClient

        class TimeoutModel:
            model = "test-model"
            supports_prompt_cache = False
            last_completion_metadata = {}

            def complete(self, prompt, max_new_tokens, **kwargs):
                raise TimeoutError("connection timed out after 30s")

        from repo_harness import SessionStore, WorkspaceContext
        workspace = WorkspaceContext.build(tmp_path)
        store = SessionStore(str(tmp_path / ".repo-harness" / "sessions"))
        agent = __import__("repo_harness").RepoHarness(
            model_client=TimeoutModel(),
            workspace=workspace,
            session_store=store,
            approval_policy="auto",
        )

        result = agent.ask("hello")
        assert "timeout" in result.lower() or "error" in result.lower()


class TestErrorModelMalformed:
    def test_err__malformed_output_returns_final_fallback(self, tmp_path):
        """模型返回无标签文本时，parse 兜底为 final。"""
        from repo_harness.runtime import RepoHarness

        kind, payload = RepoHarness.parse("Just a plain text response without tags")
        assert kind == "final"
        assert payload == "Just a plain text response without tags"

    def test_err__empty_output_returns_retry(self, tmp_path):
        """模型返回空文本时，parse 返回 retry。"""
        from repo_harness.runtime import RepoHarness

        kind, payload = RepoHarness.parse("")
        assert kind == "retry"


class TestErrorFilePermission:
    def test_err__read_nonexistent_path_gives_error(self, tmp_path):
        """读取不存在路径返回错误。"""
        agent = build_agent(tmp_path, [])
        result = agent.run_tool("read_file", {"path": "does/not/exist.py"})
        assert "not a file" in result.lower() or "error" in result.lower()


class TestErrorShellTimeout:
    def test_err__shell_timeout_returns_timed_out(self, tmp_path):
        """shell 命令超时返回 timed out 信息。"""
        agent = build_agent(tmp_path, [])
        sleeper = f'"{sys.executable}" -c "import time; time.sleep(100)"'
        result = agent.run_tool("run_shell", {"command": sleeper, "timeout": 1})
        assert "timed out" in result.lower() or "timeout" in result.lower()


class TestErrorPatchNoMatch:
    def test_err__patch_no_match_returns_count(self, tmp_path):
        """patch old_text 不匹配时返回出现次数。"""
        agent = build_agent(tmp_path, [])
        agent.run_tool("read_file", {"path": "README.md"})
        result = agent.run_tool("patch_file", {
            "path": "README.md",
            "old_text": "THIS_DOES_NOT_EXIST_ANYWHERE",
            "new_text": "replacement",
        })
        assert "must occur exactly once" in result

    def test_err__patch_multiple_matches_rejected(self, tmp_path):
        """patch old_text 出现多次时拒绝。"""
        agent = build_agent(tmp_path, [], extra_files={
            "multi.txt": "hello\nhello\nworld\n",
        })
        agent.run_tool("read_file", {"path": "multi.txt"})
        result = agent.run_tool("patch_file", {
            "path": "multi.txt",
            "old_text": "hello",
            "new_text": "hi",
        })
        assert "must occur exactly once" in result


class TestErrorToolValidation:
    def test_err__unknown_tool_returns_error(self, tmp_path):
        """调用不存在的工具返回错误。"""
        agent = build_agent(tmp_path, [])
        result = agent.run_tool("nonexistent_tool", {})
        assert "unknown tool" in result.lower()

    def test_err__empty_required_arg_rejected(self, tmp_path):
        """必填参数为空时拒绝。"""
        agent = build_agent(tmp_path, [])
        result = agent.run_tool("read_file", {"path": ""})
        assert "error" in result.lower()

    def test_err__shell_empty_command_rejected(self, tmp_path):
        """空命令被拒绝。"""
        agent = build_agent(tmp_path, [])
        result = agent.run_tool("run_shell", {"command": "", "timeout": 10})
        assert "error" in result.lower() or "must not be empty" in result.lower()
