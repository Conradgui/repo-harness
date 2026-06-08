import os
import json
import subprocess
import sys
import urllib.error
import zipfile
from pathlib import Path
from unittest.mock import patch

import repo_harness as harness_pkg
from repo_harness import cli as mini_cli
from repo_harness import (
    AnthropicCompatibleModelClient,
    ChatCompletionsCompatibleModelClient,
    FakeModelClient,
    RepoHarness,
    OllamaModelClient,
    OpenAICompatibleModelClient,
    SessionStore,
    WorkspaceContext,
    build_welcome,
)
from tests.helpers import build_agent, build_workspace


def test_agent_runs_tool_then_final(tmp_path):
    (tmp_path / "hello.txt").write_text("alpha\nbeta\n", encoding="utf-8")
    agent = build_agent(
        tmp_path,
        [
            '<tool>{"name":"read_file","args":{"path":"hello.txt","start":1,"end":2}}</tool>',
            "<final>Read the file successfully.</final>",
        ],
    )

    answer = agent.ask("Inspect hello.txt")

    assert answer == "Read the file successfully."
    assert any(item["role"] == "tool" and item["name"] == "read_file" for item in agent.session["history"])
    assert "hello.txt" in agent.session["memory"]["files"]


def test_agent_stores_bounded_python_file_summary_after_read(tmp_path):
    path = tmp_path / "worker.py"
    path.write_text(
        "import json\n"
        "from pathlib import Path\n\n"
        "DEFAULT_LIMIT = 3\n\n"
        "class Worker:\n"
        "    pass\n\n"
        "def build_worker():\n"
        "    return Worker()\n",
        encoding="utf-8",
    )
    agent = build_agent(
        tmp_path,
        [
            '<tool>{"name":"read_file","args":{"path":"worker.py","start":1,"end":20}}</tool>',
            "<final>Read worker.py.</final>",
        ],
    )

    assert agent.ask("Inspect worker.py") == "Read worker.py."
    summary = agent.session["memory"]["file_summaries"]["worker.py"]["summary"]

    assert summary == "Python: imports=json,pathlib; classes=Worker; funcs=build_worker; constants=DEFAULT_LIMIT"
    assert len(summary) <= 180
    assert summary in agent.memory.render_memory_text()

    path.write_text("print('changed')\n", encoding="utf-8")

    assert summary not in agent.memory.render_memory_text()


def test_agent_stores_markdown_structure_summary_after_complete_read(tmp_path):
    path = tmp_path / "notes.md"
    path.write_text(
        "# Roadmap\n\n"
        "```sh\n"
        "# Not a heading\n"
        "```\n\n"
        "## Phase 1\n"
        "## Phase 2\n",
        encoding="utf-8",
    )
    agent = build_agent(
        tmp_path,
        [
            '<tool>{"name":"read_file","args":{"path":"notes.md","start":1,"end":20}}</tool>',
            "<final>Read notes.md.</final>",
        ],
    )

    assert agent.ask("Inspect notes.md") == "Read notes.md."
    summary = agent.session["memory"]["file_summaries"]["notes.md"]["summary"]

    assert summary == "Markdown: headings=Roadmap,Phase 1,Phase 2"
    assert summary in agent.memory.render_memory_text()

    path.write_text("# Changed\n", encoding="utf-8")

    assert summary not in agent.memory.render_memory_text()


def test_agent_stores_config_and_test_file_structure_summaries_after_complete_reads(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"name":"demo","scripts":{},"dependencies":{}}\n',
        encoding="utf-8",
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_sample.py").write_text(
        "def helper():\n"
        "    pass\n\n"
        "def test_top_level():\n"
        "    pass\n\n"
        "class TestWorkflow:\n"
        "    def test_runs(self):\n"
        "        pass\n",
        encoding="utf-8",
    )
    agent = build_agent(
        tmp_path,
        [
            '<tool>{"name":"read_file","args":{"path":"package.json","start":1,"end":20}}</tool>',
            "<final>Read package.json.</final>",
            '<tool>{"name":"read_file","args":{"path":"tests/test_sample.py","start":1,"end":20}}</tool>',
            "<final>Read tests/test_sample.py.</final>",
        ],
    )

    assert agent.ask("Inspect package.json") == "Read package.json."
    assert agent.session["memory"]["file_summaries"]["package.json"]["summary"] == "Config: keys=name,scripts,dependencies"

    assert agent.ask("Inspect tests/test_sample.py") == "Read tests/test_sample.py."
    assert (
        agent.session["memory"]["file_summaries"]["tests/test_sample.py"]["summary"]
        == "Tests: tests=test_top_level,TestWorkflow.test_runs; classes=TestWorkflow"
    )


def test_agent_keeps_python_partial_reads_as_legacy_summary(tmp_path):
    path = tmp_path / "large.py"
    path.write_text(
        "import json\n\n"
        "class VisiblePrefix:\n"
        "    pass\n\n"
        "def later_function():\n"
        "    return VisiblePrefix()\n",
        encoding="utf-8",
    )
    agent = build_agent(
        tmp_path,
        [
            '<tool>{"name":"read_file","args":{"path":"large.py","start":1,"end":4}}</tool>',
            "<final>Read part of large.py.</final>",
        ],
    )

    assert agent.ask("Inspect the top of large.py") == "Read part of large.py."
    summary = agent.session["memory"]["file_summaries"]["large.py"]["summary"]

    assert summary == "1: import json | 2: | 3: class VisiblePrefix:"


def test_agent_updates_task_summary_on_each_request(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            "<final>First pass.</final>",
            "<final>Second pass.</final>",
        ],
    )

    assert agent.ask("First request") == "First pass."
    assert agent.session["memory"]["working"]["task_summary"] == "First request"

    assert agent.ask("Second request") == "Second pass."
    assert agent.session["memory"]["working"]["task_summary"] == "Second request"


def test_agent_only_stores_reusable_epistemic_notes(tmp_path):
    (tmp_path / "facts.txt").write_text("deploy key is red\n", encoding="utf-8")
    agent = build_agent(
        tmp_path,
        [
            '<tool>{"name":"read_file","args":{"path":"facts.txt","start":1,"end":1}}</tool>',
            "<final>Done.</final>",
            "<final>It is red.</final>",
        ],
    )

    assert agent.ask("Read the file and remember the fact") == "Done."
    notes = agent.session["memory"]["episodic_notes"]
    assert any("deploy key is red" in note["text"] for note in notes)
    assert not any(note["text"] == "Done." for note in notes)
    assert not any(note["text"] == "Done." for note in notes)

    resumed = RepoHarness.from_session(
        model_client=FakeModelClient(["<final>It is red.</final>"]),
        workspace=agent.workspace,
        session_store=agent.session_store,
        session_id=agent.session["id"],
        approval_policy="auto",
    )

    assert resumed.ask("What color is the deploy key?") == "It is red."
    prompt = resumed.model_client.prompts[-1]
    assert "Relevant memory" in prompt
    assert "deploy key is red" in prompt


def test_file_summary_cache_is_invalidated_on_out_of_band_edit_and_path_spelling(tmp_path):
    file_path = tmp_path / "sample.txt"
    file_path.write_text("alpha\n", encoding="utf-8")
    agent = build_agent(tmp_path, [])

    agent.memory.set_file_summary("./sample.txt", "sample.txt: alpha")
    agent.memory.remember_file("./sample.txt")
    assert agent.memory.to_dict()["file_summaries"]["sample.txt"]["freshness"]

    assert "sample.txt: alpha" in agent.memory.render_memory_text()
    file_path.write_text("beta\n", encoding="utf-8")

    resumed = RepoHarness.from_session(
        model_client=FakeModelClient([]),
        workspace=agent.workspace,
        session_store=agent.session_store,
        session_id=agent.session["id"],
        approval_policy="auto",
    )

    assert "sample.txt: alpha" not in resumed.memory_text()
    resumed.memory.invalidate_file_summary("sample.txt")
    assert "sample.txt" not in resumed.memory.to_dict()["file_summaries"]


def test_agent_retries_after_empty_model_output(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            "",
            "<final>Recovered after retry.</final>",
        ],
    )

    answer = agent.ask("Do the task")

    assert answer == "Recovered after retry."
    notices = [item["content"] for item in agent.session["history"] if item["role"] == "assistant"]
    assert any("empty response" in item for item in notices)


def test_agent_retries_after_malformed_tool_payload(tmp_path):
    (tmp_path / "hello.txt").write_text("alpha\n", encoding="utf-8")
    agent = build_agent(
        tmp_path,
        [
            '<tool>{"name":"read_file","args":"bad"}</tool>',
            '<tool>{"name":"read_file","args":{"path":"hello.txt","start":1,"end":1}}</tool>',
            "<final>Recovered after malformed tool output.</final>",
        ],
    )

    answer = agent.ask("Inspect hello.txt")

    assert answer == "Recovered after malformed tool output."
    assert any(item["role"] == "tool" and item["name"] == "read_file" for item in agent.session["history"])
    notices = [item["content"] for item in agent.session["history"] if item["role"] == "assistant"]
    assert any("valid <tool> call" in item for item in notices)


def test_agent_accepts_xml_write_file_tool(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            '<tool name="write_file" path="hello.py"><content>print("hi")\n</content></tool>',
            "<final>Done.</final>",
        ],
    )

    answer = agent.ask("Create hello.py")

    assert answer == "Done."
    assert (tmp_path / "hello.py").read_text(encoding="utf-8") == 'print("hi")\n'


def test_retries_do_not_consume_the_whole_budget(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            "",
            "",
            "<final>Recovered after several retries.</final>",
        ],
        max_steps=1,
    )

    answer = agent.ask("Do the task")

    assert answer == "Recovered after several retries."


def test_agent_saves_and_resumes_session(tmp_path):
    agent = build_agent(tmp_path, ["<final>First pass.</final>"])
    assert agent.ask("Start a session") == "First pass."

    resumed = RepoHarness.from_session(
        model_client=FakeModelClient(["<final>Resumed.</final>"]),
        workspace=agent.workspace,
        session_store=agent.session_store,
        session_id=agent.session["id"],
        approval_policy="auto",
    )

    assert resumed.session["history"][0]["content"] == "Start a session"
    assert resumed.ask("Continue") == "Resumed."


def test_delegate_uses_child_agent(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            '<tool>{"name":"delegate","args":{"task":"inspect README","max_steps":2}}</tool>',
            "<final>Child result.</final>",
            "<final>Parent incorporated the child result.</final>",
        ],
    )

    answer = agent.ask("Use delegation")

    assert answer == "Parent incorporated the child result."
    tool_events = [item for item in agent.session["history"] if item["role"] == "tool"]
    assert tool_events[0]["name"] == "delegate"
    assert "delegate_result" in tool_events[0]["content"]


def test_patch_file_replaces_exact_match(tmp_path):
    file_path = tmp_path / "sample.txt"
    file_path.write_text("hello world\n", encoding="utf-8")
    agent = build_agent(tmp_path, [])
    agent.run_tool("read_file", {"path": "sample.txt", "start": 1, "end": 10})

    result = agent.run_tool(
        "patch_file",
        {
            "path": "sample.txt",
            "old_text": "world",
            "new_text": "agent",
        },
    )

    assert result == "patched sample.txt"
    assert file_path.read_text(encoding="utf-8") == "hello agent\n"


def test_invalid_risky_tool_does_not_prompt_for_approval(tmp_path):
    agent = build_agent(tmp_path, [], approval_policy="ask")

    with patch("builtins.input") as mock_input:
        result = agent.run_tool("write_file", {})

    assert result.startswith("error: invalid arguments for write_file: 'path'")
    assert 'example: <tool name="write_file"' in result
    mock_input.assert_not_called()


def test_list_files_hides_internal_agent_state(tmp_path):
    agent = build_agent(tmp_path, [])
    (tmp_path / ".repo-harness").mkdir(exist_ok=True)
    (tmp_path / ".git").mkdir(exist_ok=True)
    (tmp_path / "hello.txt").write_text("hi\n", encoding="utf-8")

    result = agent.run_tool("list_files", {})

    assert ".repo-harness" not in result
    assert ".git" not in result
    assert "[F] hello.txt" in result


def test_repeated_identical_tool_call_is_rejected(tmp_path):
    agent = build_agent(tmp_path, [])
    agent.record({"role": "tool", "name": "list_files", "args": {}, "content": "(empty)", "created_at": "1"})
    agent.record({"role": "tool", "name": "list_files", "args": {}, "content": "(empty)", "created_at": "2"})

    result = agent.run_tool("list_files", {})

    assert result == "error: repeated identical tool call for list_files; choose a different tool or return a final answer"


def test_run_shell_workspace_search_is_rejected_by_tool_policy(tmp_path):
    agent = build_agent(tmp_path, [], approval_policy="auto")

    result = agent.run_tool("run_shell", {"command": "rg hello .", "timeout": 20})

    assert "tool policy rejected run_shell" in result
    assert "use search/read_file/list_files" in result
    assert agent._last_tool_result_metadata["tool_error_code"] == "tool_policy_workspace_read"


def test_run_shell_pipeline_tail_is_allowed_by_tool_policy(tmp_path):
    agent = build_agent(tmp_path, [], approval_policy="auto")

    result = agent.run_tool("run_shell", {"command": "printf 'a\\nb\\n' | tail -n 1", "timeout": 20})

    assert "exit_code: 0" in result
    assert "b" in result


def test_write_file_existing_path_requires_fresh_read(tmp_path):
    (tmp_path / "sample.txt").write_text("old\n", encoding="utf-8")
    agent = build_agent(tmp_path, [], approval_policy="auto")

    rejected = agent.run_tool("write_file", {"path": "sample.txt", "content": "new\n"})
    agent.run_tool("read_file", {"path": "sample.txt", "start": 1, "end": 10})
    accepted = agent.run_tool("write_file", {"path": "sample.txt", "content": "new\n"})

    assert "fresh read_file" in rejected
    assert accepted == "wrote sample.txt (4 chars)"
    assert (tmp_path / "sample.txt").read_text(encoding="utf-8") == "new\n"


def test_patch_file_existing_path_requires_fresh_read(tmp_path):
    (tmp_path / "sample.txt").write_text("old\n", encoding="utf-8")
    agent = build_agent(tmp_path, [], approval_policy="auto")

    rejected = agent.run_tool("patch_file", {"path": "sample.txt", "old_text": "old", "new_text": "new"})
    agent.run_tool("read_file", {"path": "sample.txt", "start": 1, "end": 10})
    accepted = agent.run_tool("patch_file", {"path": "sample.txt", "old_text": "old", "new_text": "new"})

    assert "fresh read_file" in rejected
    assert accepted == "patched sample.txt"


def test_welcome_screen_keeps_box_shape_for_long_paths(tmp_path):
    deep = tmp_path / "very" / "long" / "path" / "for" / "the" / "mini" / "agent" / "welcome" / "screen"
    deep.mkdir(parents=True)
    agent = build_agent(deep, [])

    welcome = build_welcome(agent, model="qwen3.5:4b", host="http://127.0.0.1:11434")
    lines = welcome.splitlines()

    assert len(lines) >= 5
    assert len({len(line) for line in lines}) == 1
    assert "..." in welcome
    assert "(  o o  )" in welcome
    assert "MINI-CODING-AGENT" not in welcome
    assert "MINI CODING AGENT" not in welcome
    assert "RepoHarness" in welcome
    assert "local repository harness" in welcome
    assert "// READY" not in welcome
    assert "SLASH" not in welcome
    assert "READY      " not in welcome
    assert "commands: Commands:" not in welcome


def test_ollama_client_posts_expected_payload():
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"response": "<final>ok</final>"}).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    client = OllamaModelClient(
        model="qwen3.5:4b",
        host="http://127.0.0.1:11434",
        temperature=0.2,
        top_p=0.9,
        timeout=30,
    )

    with patch("urllib.request.urlopen", fake_urlopen):
        result = client.complete("hello", 42)

    assert result == "<final>ok</final>"
    assert captured["url"] == "http://127.0.0.1:11434/api/generate"
    assert captured["timeout"] == 30
    assert captured["body"]["model"] == "qwen3.5:4b"
    assert captured["body"]["prompt"] == "hello"
    assert captured["body"]["stream"] is False


def test_openai_compatible_client_posts_expected_responses_payload():
    captured = {}

    class FakeResponse:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"output_text": "<final>ok</final>"}).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    client = OpenAICompatibleModelClient(
        model="right.codes/codex-mini",
        base_url="https://right.codes/v1",
        api_key="sk-test",
        temperature=0.2,
        timeout=30,
    )

    with patch("urllib.request.urlopen", fake_urlopen):
        result = client.complete("hello", 42)

    assert result == "<final>ok</final>"
    assert captured["url"] == "https://right.codes/v1/responses"
    assert captured["timeout"] == 30
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["headers"]["Content-type"] == "application/json"
    assert captured["body"] == {
        "model": "right.codes/codex-mini",
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "hello",
                    }
                ],
            }
        ],
        "max_output_tokens": 42,
        "stream": False,
        "temperature": 0.2,
    }


def test_chat_completions_client_posts_expected_payload_and_records_usage():
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "choices": [{"message": {"content": "<final>chat ok</final>"}}],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                    },
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    client = ChatCompletionsCompatibleModelClient(
        model="mimo-v2.5-pro",
        base_url="https://token-plan-cn.xiaomimimo.com/v1",
        api_key="mimo-key",
        temperature=0.2,
        timeout=30,
    )

    with patch("urllib.request.urlopen", fake_urlopen):
        result = client.complete("hello", 42)

    assert result == "<final>chat ok</final>"
    assert captured["url"] == "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"
    assert captured["timeout"] == 30
    assert captured["headers"]["Authorization"] == "Bearer mimo-key"
    assert captured["body"] == {
        "model": "mimo-v2.5-pro",
        "messages": [{"role": "user", "content": "hello"}],
        "max_tokens": 42,
        "stream": False,
        "temperature": 0.2,
    }
    assert client.last_completion_metadata["provider_protocol"] == "chat-completions-compatible"
    assert client.last_completion_metadata["provider_model"] == "mimo-v2.5-pro"
    assert client.last_completion_metadata["provider_base_url"] == "https://token-plan-cn.xiaomimimo.com/v1"
    assert client.last_completion_metadata["input_tokens"] == 10
    assert client.last_completion_metadata["output_tokens"] == 5
    assert client.last_completion_metadata["total_tokens"] == 15


def test_chat_completions_provider_retry_metadata_records_retry_count():
    calls = {"count": 0}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": "<final>ok</final>"}}]}).encode("utf-8")

    def fake_urlopen(request, timeout):
        del timeout
        calls["count"] += 1
        if calls["count"] == 1:
            raise urllib.error.HTTPError(
                url=request.full_url,
                code=429,
                msg="too many requests",
                hdrs={},
                fp=None,
            )
        return FakeResponse()

    client = ChatCompletionsCompatibleModelClient(
        model="chat-test",
        base_url="https://token@example.test/v1?api_key=secret#fragment",
        api_key="chat-key",
        temperature=0.2,
        timeout=30,
    )

    with patch("time.sleep"), patch("urllib.request.urlopen", fake_urlopen):
        result = client.complete("hello", 42)

    assert result == "<final>ok</final>"
    assert client.last_completion_metadata["provider_base_url"] == "https://example.test/v1"
    assert client.last_completion_metadata["provider_attempts"] == 2
    assert client.last_completion_metadata["provider_retry_count"] == 1


def test_openai_compatible_client_sends_prompt_cache_fields_and_records_usage():
    captured = {}

    class FakeResponse:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "output_text": "<final>ok</final>",
                    "usage": {
                        "input_tokens": 2048,
                        "input_tokens_details": {"cached_tokens": 1536},
                        "output_tokens": 32,
                        "total_tokens": 2080,
                    },
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    client = OpenAICompatibleModelClient(
        model="right.codes/codex-mini",
        base_url="https://right.codes/v1",
        api_key="sk-test",
        temperature=0.2,
        timeout=30,
    )

    with patch("urllib.request.urlopen", fake_urlopen):
        result = client.complete(
            "hello",
            42,
            prompt_cache_key="prefix-hash-123",
            prompt_cache_retention="in_memory",
        )

    assert result == "<final>ok</final>"
    assert captured["body"]["prompt_cache_key"] == "prefix-hash-123"
    assert captured["body"]["prompt_cache_retention"] == "in_memory"
    assert client.last_completion_metadata["prompt_cache_supported"] is True
    assert client.last_completion_metadata["cached_tokens"] == 1536
    assert client.last_completion_metadata["cache_hit"] is True
    assert client.last_completion_metadata["input_tokens"] == 2048
    assert client.last_completion_metadata["provider_protocol"] == "openai-compatible"
    assert client.last_completion_metadata["provider_model"] == "right.codes/codex-mini"
    assert client.last_completion_metadata["provider_base_url"] == "https://right.codes/v1"
    assert client.last_completion_metadata["provider_attempts"] == 1
    assert client.last_completion_metadata["provider_retry_count"] == 0


def test_openai_provider_retry_metadata_records_retry_count_and_sanitized_url():
    calls = {"count": 0}

    class FakeResponse:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"output_text": "<final>ok</final>"}).encode("utf-8")

    def fake_urlopen(request, timeout):
        del request, timeout
        calls["count"] += 1
        if calls["count"] == 1:
            raise urllib.error.HTTPError(
                url="https://example.test/v1/responses",
                code=429,
                msg="too many requests",
                hdrs={},
                fp=None,
            )
        return FakeResponse()

    client = OpenAICompatibleModelClient(
        model="gpt-test",
        base_url="https://token@example.test/v1?api_key=secret#fragment",
        api_key="sk-test",
        temperature=0.2,
        timeout=30,
    )

    with patch("time.sleep"), patch("urllib.request.urlopen", fake_urlopen):
        result = client.complete("hello", 42)

    assert result == "<final>ok</final>"
    assert client.last_completion_metadata["provider_base_url"] == "https://example.test/v1"
    assert client.last_completion_metadata["provider_attempts"] == 2
    assert client.last_completion_metadata["provider_retry_count"] == 1


def test_anthropic_provider_non_retryable_4xx_fails_fast():
    calls = {"count": 0}

    def fake_urlopen(request, timeout):
        del request, timeout
        calls["count"] += 1
        raise urllib.error.HTTPError(
            url="https://example.test/messages",
            code=400,
            msg="bad request",
            hdrs={},
            fp=None,
        )

    client = AnthropicCompatibleModelClient(
        model="claude-test",
        base_url="https://example.test",
        api_key="sk-test",
        temperature=0.2,
        timeout=30,
    )

    with patch("urllib.request.urlopen", fake_urlopen):
        try:
            client.complete("hello", 42)
        except RuntimeError as exc:
            assert "HTTP 400" in str(exc)
        else:
            raise AssertionError("non-retryable 4xx should fail")

    assert calls["count"] == 1
    assert client.last_completion_metadata["provider_attempts"] == 1
    assert client.last_completion_metadata["provider_retry_count"] == 0


def test_openai_compatible_client_extracts_text_from_event_stream():
    class FakeResponse:
        headers = {"Content-Type": "text/event-stream"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return (
                'data: {"type":"response.created","response":{"id":"resp_1","output":[]}}\n'
                'data: {"type":"response.completed","response":{"output":[{"content":[{"text":"<final>stream ok</final>"}]}]}}\n'
                "data: [DONE]\n"
            ).encode("utf-8")

    client = OpenAICompatibleModelClient(
        model="right.codes/codex-mini",
        base_url="https://right.codes/v1",
        api_key="sk-test",
        temperature=0.2,
        timeout=30,
    )

    with patch("urllib.request.urlopen", return_value=FakeResponse()):
        result = client.complete("hello", 42)

    assert result == "<final>stream ok</final>"


def test_openai_compatible_client_extracts_text_from_event_stream_deltas():
    class FakeResponse:
        headers = {"Content-Type": "text/event-stream"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return (
                'event: response.output_text.delta\n'
                'data: {"type":"response.output_text.delta","delta":"<final>"}\n'
                'event: response.output_text.delta\n'
                'data: {"type":"response.output_text.delta","delta":"OK"}\n'
                'event: response.output_text.done\n'
                'data: {"type":"response.output_text.done","text":"<final>OK</final>"}\n'
                "data: [DONE]\n"
            ).encode("utf-8")

    client = OpenAICompatibleModelClient(
        model="right.codes/codex-mini",
        base_url="https://right.codes/v1",
        api_key="sk-test",
        temperature=0.2,
        timeout=30,
    )

    with patch("urllib.request.urlopen", return_value=FakeResponse()):
        result = client.complete("hello", 42)

    assert result == "<final>OK</final>"


def test_anthropic_compatible_client_posts_expected_messages_payload():
    captured = {}

    class FakeResponse:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "content": [
                        {
                            "type": "text",
                            "text": "<final>ok</final>",
                        }
                    ]
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    client = AnthropicCompatibleModelClient(
        model="claude-sonnet-4-5-20250929",
        base_url="https://www.right.codes/claude-aws/v1",
        api_key="sk-test",
        temperature=0.2,
        timeout=30,
    )

    with patch("urllib.request.urlopen", fake_urlopen):
        result = client.complete("hello", 42)

    assert result == "<final>ok</final>"
    assert captured["url"] == "https://www.right.codes/claude-aws/v1/messages"
    assert captured["timeout"] == 30
    assert captured["headers"]["X-api-key"] == "sk-test"
    assert captured["headers"]["Anthropic-version"] == "2023-06-01"
    assert captured["headers"]["Content-type"] == "application/json"
    assert captured["body"] == {
        "model": "claude-sonnet-4-5-20250929",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "hello",
                    }
                ],
            }
        ],
        "max_tokens": 42,
        "stream": False,
        "temperature": 0.2,
    }


def test_anthropic_compatible_client_extracts_first_text_block():
    class FakeResponse:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "content": [
                        {"type": "thinking", "thinking": "hidden"},
                        {"type": "text", "text": "<final>ok</final>"},
                    ]
                }
            ).encode("utf-8")

    client = AnthropicCompatibleModelClient(
        model="claude-sonnet-4-5-20250929",
        base_url="https://www.right.codes/claude-aws/v1",
        api_key="sk-test",
        temperature=0.2,
        timeout=30,
    )

    with patch("urllib.request.urlopen", return_value=FakeResponse()):
        result = client.complete("hello", 42)

    assert result == "<final>ok</final>"


def test_build_agent_uses_openai_provider_and_model_override(tmp_path):
    args = type(
        "Args",
        (),
        {
            "cwd": str(tmp_path),
            "provider": "openai",
            "model": "override-model",
            "base_url": None,
            "host": "http://127.0.0.1:11434",
            "ollama_timeout": 300,
            "temperature": 0.2,
            "top_p": 0.9,
            "resume": None,
            "approval": "ask",
            "secret_env_names": [],
            "max_steps": 6,
            "max_new_tokens": 512,
        },
    )()

    with patch.dict(
        os.environ,
        {
            "OPENAI_API_BASE": "https://www.right.codes/codex/v1",
            "OPENAI_API_KEY": "sk-test",
            "OPENAI_MODEL": "env-model",
        },
        clear=False,
    ):
        with patch(
            "repo_harness.cli.OllamaModelClient",
            side_effect=AssertionError("ollama client should not be used"),
        ), patch("repo_harness.cli.OpenAICompatibleModelClient") as mock_openai:
            fake_client = mock_openai.return_value
            agent = harness_pkg.build_agent(args)

    mock_openai.assert_called_once()
    assert mock_openai.call_args.kwargs["model"] == "override-model"
    assert mock_openai.call_args.kwargs["base_url"] == "https://www.right.codes/codex/v1"
    assert mock_openai.call_args.kwargs["api_key"] == "sk-test"
    assert agent.model_client is fake_client


def test_build_arg_parser_defaults_provider_to_openai(tmp_path):
    args = harness_pkg.build_arg_parser().parse_args(["--cwd", str(tmp_path)])

    assert args.provider == "openai"


def test_build_arg_parser_accepts_anthropic_provider(tmp_path):
    args = harness_pkg.build_arg_parser().parse_args(["--cwd", str(tmp_path), "--provider", "anthropic"])

    assert args.provider == "anthropic"


def test_build_arg_parser_accepts_deepseek_provider(tmp_path):
    args = harness_pkg.build_arg_parser().parse_args(["--cwd", str(tmp_path), "--provider", "deepseek"])

    assert args.provider == "deepseek"


def test_build_arg_parser_accepts_chat_completions_provider(tmp_path):
    args = harness_pkg.build_arg_parser().parse_args(["--cwd", str(tmp_path), "--provider", "chat-completions"])

    assert args.provider == "chat-completions"


def test_build_agent_uses_chat_completions_provider_from_repo_harness_toml(tmp_path):
    (tmp_path / ".repo-harness.toml").write_text(
        "\n".join(
            [
                'provider = "chat-completions"',
                "",
                "[providers.chat-completions]",
                'model = "mimo-v2.5-pro"',
                'base_url = "https://token-plan-cn.xiaomimimo.com/v1"',
                'api_key_env = "VENDOR_CHAT_API_KEY"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    args = harness_pkg.build_arg_parser().parse_args(["--cwd", str(tmp_path)])

    with patch.dict(os.environ, {"VENDOR_CHAT_API_KEY": "vendor-chat-key"}, clear=True), patch(
        "repo_harness.cli.ChatCompletionsCompatibleModelClient"
    ) as mock_chat:
        agent = harness_pkg.build_agent(args)

    mock_chat.assert_called_once()
    assert mock_chat.call_args.kwargs["model"] == "mimo-v2.5-pro"
    assert mock_chat.call_args.kwargs["base_url"] == "https://token-plan-cn.xiaomimimo.com/v1"
    assert mock_chat.call_args.kwargs["api_key"] == "vendor-chat-key"
    assert agent.model_client is mock_chat.return_value


def test_build_agent_uses_chat_completions_environment_overrides(tmp_path):
    args = harness_pkg.build_arg_parser().parse_args(["--cwd", str(tmp_path), "--provider", "chat-completions"])

    with patch.dict(
        os.environ,
        {
            "CHAT_COMPLETIONS_API_KEY": "chat-key",
            "CHAT_COMPLETIONS_API_BASE": "https://chat.example/v1",
            "CHAT_COMPLETIONS_MODEL": "chat-model",
        },
        clear=True,
    ), patch("repo_harness.cli.ChatCompletionsCompatibleModelClient") as mock_chat:
        harness_pkg.build_agent(args)

    assert mock_chat.call_args.kwargs["model"] == "chat-model"
    assert mock_chat.call_args.kwargs["base_url"] == "https://chat.example/v1"
    assert mock_chat.call_args.kwargs["api_key"] == "chat-key"


def test_build_agent_uses_deepseek_provider_from_repo_harness_toml(tmp_path):
    (tmp_path / ".repo-harness.toml").write_text(
        "\n".join(
            [
                'provider = "deepseek"',
                "max_steps = 50",
                "max_tokens = 4096",
                "",
                "[providers.deepseek]",
                'client = "anthropic"',
                'model = "deepseek-chat"',
                'base_url = "https://api.deepseek.com/anthropic?api_key=secret#frag"',
                'api_key_env = "DEEPSEEK_API_KEY"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    args = harness_pkg.build_arg_parser().parse_args(["--cwd", str(tmp_path)])

    with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-deepseek"}, clear=True), patch(
        "repo_harness.cli.AnthropicCompatibleModelClient"
    ) as mock_anthropic:
        agent = harness_pkg.build_agent(args)

    mock_anthropic.assert_called_once()
    assert mock_anthropic.call_args.kwargs["model"] == "deepseek-chat"
    assert mock_anthropic.call_args.kwargs["base_url"] == "https://api.deepseek.com/anthropic?api_key=secret#frag"
    assert mock_anthropic.call_args.kwargs["api_key"] == "sk-deepseek"
    assert agent.max_steps == 50
    assert agent.max_new_tokens == 4096


def test_cli_explicit_model_and_base_url_override_repo_harness_toml(tmp_path):
    (tmp_path / ".repo-harness.toml").write_text(
        "\n".join(
            [
                'provider = "deepseek"',
                "",
                "[providers.deepseek]",
                'client = "anthropic"',
                'model = "toml-model"',
                'base_url = "https://toml.example/anthropic"',
                'api_key_env = "DEEPSEEK_API_KEY"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    args = harness_pkg.build_arg_parser().parse_args(
        [
            "--cwd",
            str(tmp_path),
            "--model",
            "cli-model",
            "--base-url",
            "https://cli.example/anthropic",
        ]
    )

    with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-deepseek"}, clear=True), patch(
        "repo_harness.cli.AnthropicCompatibleModelClient"
    ) as mock_anthropic:
        harness_pkg.build_agent(args)

    assert mock_anthropic.call_args.kwargs["model"] == "cli-model"
    assert mock_anthropic.call_args.kwargs["base_url"] == "https://cli.example/anthropic"


def test_repo_harness_toml_max_tokens_alias_sets_max_new_tokens(tmp_path):
    (tmp_path / ".repo-harness.toml").write_text(
        'provider = "openai"\nmax_tokens = 1234\n',
        encoding="utf-8",
    )
    args = harness_pkg.build_arg_parser().parse_args(["--cwd", str(tmp_path)])

    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-openai"}, clear=True), patch(
        "repo_harness.cli.OpenAICompatibleModelClient"
    ):
        agent = harness_pkg.build_agent(args)

    assert agent.max_new_tokens == 1234


def test_build_agent_uses_anthropic_provider_and_openai_key_fallback(tmp_path):
    args = type(
        "Args",
        (),
        {
            "cwd": str(tmp_path),
            "provider": "anthropic",
            "model": "claude-sonnet-4-5-20250929",
            "base_url": None,
            "host": "http://127.0.0.1:11434",
            "ollama_timeout": 300,
            "openai_timeout": 300,
            "temperature": 0.2,
            "top_p": 0.9,
            "resume": None,
            "approval": "ask",
            "secret_env_names": [],
            "max_steps": 6,
            "max_new_tokens": 512,
        },
    )()

    with patch.dict(
        os.environ,
        {
            "OPENAI_API_KEY": "sk-openai-fallback",
        },
        clear=True,
    ):
        with patch(
            "repo_harness.cli.OllamaModelClient",
            side_effect=AssertionError("ollama client should not be used"),
        ), patch(
            "repo_harness.cli.OpenAICompatibleModelClient",
            side_effect=AssertionError("openai client should not be used"),
        ), patch("repo_harness.cli.AnthropicCompatibleModelClient") as mock_anthropic:
            fake_client = mock_anthropic.return_value
            agent = harness_pkg.build_agent(args)

    mock_anthropic.assert_called_once()
    assert mock_anthropic.call_args.kwargs["model"] == "claude-sonnet-4-5-20250929"
    assert mock_anthropic.call_args.kwargs["base_url"] == "https://api.anthropic.com"
    assert mock_anthropic.call_args.kwargs["api_key"] == "sk-openai-fallback"
    assert agent.model_client is fake_client


def test_build_agent_uses_anthropic_default_model_when_env_is_missing(tmp_path):
    args = harness_pkg.build_arg_parser().parse_args(["--cwd", str(tmp_path), "--provider", "anthropic"])

    with patch.dict(
        os.environ,
        {},
        clear=False,
    ):
        os.environ.pop("ANTHROPIC_MODEL", None)
        with patch("repo_harness.cli.AnthropicCompatibleModelClient") as mock_anthropic:
            harness_pkg.build_agent(args)

    assert mock_anthropic.call_args.kwargs["model"] == "claude-sonnet-4-6"


def test_build_agent_uses_openai_provider_by_default(tmp_path):
    args = harness_pkg.build_arg_parser().parse_args(["--cwd", str(tmp_path)])

    with patch.dict(
        os.environ,
        {
            "OPENAI_API_BASE": "https://www.right.codes/codex/v1",
            "OPENAI_API_KEY": "sk-test",
        },
        clear=False,
    ):
        with patch(
            "repo_harness.cli.OllamaModelClient",
            side_effect=AssertionError("ollama client should not be used"),
        ), patch("repo_harness.cli.OpenAICompatibleModelClient") as mock_openai:
            fake_client = mock_openai.return_value
            agent = harness_pkg.build_agent(args)

    mock_openai.assert_called_once()
    assert mock_openai.call_args.kwargs["model"] == "gpt-5.4"
    assert mock_openai.call_args.kwargs["base_url"] == "https://www.right.codes/codex/v1"
    assert mock_openai.call_args.kwargs["api_key"] == "sk-test"
    assert agent.model_client is fake_client


def test_successful_run_persists_run_artifacts_and_stop_reason(tmp_path):
    (tmp_path / "hello.txt").write_text("alpha\nbeta\n", encoding="utf-8")
    agent = build_agent(
        tmp_path,
        [
            '<tool>{"name":"read_file","args":{"path":"hello.txt","start":1,"end":2}}</tool>',
            "<final>Finished.</final>",
        ],
    )

    assert agent.ask("Do the thing") == "Finished."

    runs_root = tmp_path / ".repo-harness" / "runs"
    run_dirs = [path for path in runs_root.iterdir() if path.is_dir()]
    assert len(run_dirs) == 1

    run_dir = run_dirs[0]
    task_state = json.loads((run_dir / "task_state.json").read_text(encoding="utf-8"))
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    trace_lines = (run_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()

    assert task_state["task_id"] != task_state["run_id"]
    assert run_dir.name == task_state["run_id"]
    assert (run_dir / "task_state.json").exists()
    assert (run_dir / "trace.jsonl").exists()
    assert (run_dir / "report.json").exists()
    assert task_state["stop_reason"] == "final_answer_returned"
    assert task_state["final_answer"] == "Finished."
    assert report["stop_reason"] == "final_answer_returned"
    assert report["task_state"]["stop_reason"] == "final_answer_returned"
    assert report["run_id"] == task_state["run_id"]
    trace_events = [json.loads(line)["event"] for line in trace_lines]
    assert trace_events[0] == "run_started"
    assert trace_events[-1] == "run_finished"
    assert trace_events.count("prompt_built") == 2
    assert "tool_executed" in trace_events


def test_trace_and_report_redact_secret_env_values(tmp_path):
    secret = "sk-test-secret-123"
    with patch.dict(os.environ, {"OPENAI_API_KEY": secret}, clear=True):
        agent = build_agent(
            tmp_path,
            [
                '<tool>{"name":"run_shell","args":{"command":"printf \'%s\' \'sk-test-secret-123\'","timeout":20}}</tool>',
                "<final>Masked.</final>",
            ],
        )

        assert agent.ask("Mask the secret") == "Masked."

    runs_root = tmp_path / ".repo-harness" / "runs"
    run_dirs = [path for path in runs_root.iterdir() if path.is_dir()]
    assert len(run_dirs) == 1

    run_dir = run_dirs[0]
    trace_text = (run_dir / "trace.jsonl").read_text(encoding="utf-8")
    report_text = (run_dir / "report.json").read_text(encoding="utf-8")
    trace_events = [json.loads(line) for line in trace_text.splitlines()]

    assert secret not in trace_text
    assert secret not in report_text

    prompt_events = [event for event in trace_events if event["event"] == "prompt_built"]
    assert prompt_events
    assert prompt_events[0]["prompt_metadata"]["secret_env_count"] >= 1
    assert "OPENAI_API_KEY" in prompt_events[0]["prompt_metadata"]["secret_env_names"]

    tool_events = [event for event in trace_events if event["event"] == "tool_executed"]
    assert tool_events
    assert "<redacted>" in tool_events[0]["args"]["command"]
    assert "<redacted>" in tool_events[0]["result"]


def test_prompt_budget_metadata_records_budget_decisions(tmp_path):
    agent = build_agent(tmp_path, ["<final>Done.</final>"])
    agent.memory.append_note("alpha episodic note " + ("A" * 120), tags=("recall",), created_at="2026-04-07T10:00:00+00:00")
    agent.memory.append_note("beta episodic recall note " + ("B" * 120), created_at="2026-04-07T10:01:00+00:00")
    agent.memory.append_note("gamma episodic note " + ("C" * 120), tags=("recall",), created_at="2026-04-07T10:02:00+00:00")

    for index in range(4):
        agent.record(
            {
                "role": "user" if index % 2 == 0 else "assistant",
                "content": f"history-{index}-" + ("A" * 240),
                "created_at": f"2026-04-07T10:0{index}:00+00:00",
            }
        )

    agent.context_manager.total_budget = 1000
    agent.context_manager.section_budgets = {
        "prefix": 80,
        "memory": 80,
        "relevant_memory": 80,
        "history": 80,
    }

    assert agent.ask("recall") == "Done."

    trace_events = [
        json.loads(line)
        for line in (agent.run_store.trace_path(agent.current_task_state).read_text(encoding="utf-8").splitlines())
    ]
    prompt_events = [event for event in trace_events if event["event"] == "prompt_built"]
    assert prompt_events
    metadata = prompt_events[0]["prompt_metadata"]
    relevant_section = agent.model_client.prompts[0].split("Relevant memory:\n", 1)[1].split("\n\nTranscript:", 1)[0]

    assert metadata["relevant_memory"]["selected_count"] == 3
    assert len(metadata["relevant_memory"]["rendered_notes"]) == 3
    assert len([line for line in relevant_section.splitlines() if line.startswith("- ")]) == 3
    assert "alpha episodic" in relevant_section
    assert "beta episodic" in relevant_section
    assert "gamma episodic" in relevant_section
    assert metadata["current_request"]["text"] == "recall"
    assert metadata["current_request"]["rendered_chars"] == len("recall")


def test_relevant_memory_explanations_are_reported_without_prompt_pollution(tmp_path):
    agent = build_agent(tmp_path, ["<final>Done.</final>"])
    agent.memory.append_note(
        "conventions prefer constrained tools",
        tags=("convention",),
        source="session",
        created_at="2026-05-06T10:00:00+00:00",
    )

    assert agent.ask("What convention covers tools?") == "Done."

    report = json.loads(agent.run_store.report_path(agent.current_task_state).read_text(encoding="utf-8"))
    relevant_metadata = report["prompt_metadata"]["relevant_memory"]
    relevant_section = agent.model_client.prompts[0].split("Relevant memory:\n", 1)[1].split("\n\nTranscript:", 1)[0]

    assert relevant_metadata["selected_explanations"]
    assert relevant_metadata["selected_explanations"][0]["text"] == "conventions prefer constrained tools"
    assert relevant_metadata["selected_explanations"][0]["score_breakdown"]["tag_match"] == 1
    assert "conventions prefer constrained tools" in relevant_section
    assert "score_breakdown" not in relevant_section
    assert "selected_explanations" not in agent.model_client.prompts[0]


def test_prompt_metadata_refreshes_prefix_when_workspace_changes(tmp_path):
    agent = build_agent(tmp_path, [])

    first = agent.prompt_metadata("first", "")
    second = agent.prompt_metadata("second", "")

    assert first["prefix_hash"] == second["prefix_hash"]
    assert second["prefix_changed"] is False
    assert second["workspace_changed"] is False

    (tmp_path / "README.md").write_text("demo changed\n", encoding="utf-8")

    third = agent.prompt_metadata("third", "")

    assert third["prefix_hash"] != second["prefix_hash"]
    assert third["prefix_changed"] is True
    assert third["workspace_changed"] is True
    assert "demo changed" in agent.prefix


def test_agent_creates_checkpoint_when_context_reduction_happens_and_artifacts_only_reference_it(tmp_path):
    agent = build_agent(tmp_path, ["<final>Done after checkpoint.</final>"])
    for index in range(10):
        agent.record(
            {
                "role": "user" if index % 2 == 0 else "assistant",
                "content": f"history-{index}-" + ("A" * 260),
                "created_at": f"2026-04-07T10:{index:02d}:00+00:00",
            }
        )
    agent.memory.append_note("checkpoint note " + ("B" * 220), tags=("checkpoint",), created_at="2026-04-07T11:00:00+00:00")
    agent.context_manager.total_budget = 900
    agent.context_manager.section_budgets = {
        "prefix": 120,
        "memory": 120,
        "relevant_memory": 120,
        "history": 160,
    }

    assert agent.ask("Resume the long task") == "Done after checkpoint."

    checkpoint_state = agent.session["checkpoints"]
    checkpoint = checkpoint_state["items"][checkpoint_state["current_id"]]
    assert checkpoint["checkpoint_id"] == checkpoint_state["current_id"]
    assert checkpoint["schema_version"] == "phase1-v1"
    assert checkpoint["current_goal"] == "Resume the long task"
    assert checkpoint["key_files"] == []
    assert checkpoint["current_blocker"] == ""
    assert checkpoint["next_step"]

    task_state = json.loads(agent.run_store.task_state_path(agent.current_task_state).read_text(encoding="utf-8"))
    report = json.loads(agent.run_store.report_path(agent.current_task_state).read_text(encoding="utf-8"))
    trace_events = [
        json.loads(line)
        for line in agent.run_store.trace_path(agent.current_task_state).read_text(encoding="utf-8").splitlines()
    ]

    assert task_state["checkpoint_id"] == checkpoint["checkpoint_id"]
    assert report["checkpoint_id"] == checkpoint["checkpoint_id"]
    assert report["task_state"]["checkpoint_id"] == checkpoint["checkpoint_id"]
    assert "current_goal" not in task_state
    assert "current_goal" not in report
    checkpoint_events = [event for event in trace_events if event["event"] == "checkpoint_created"]
    assert checkpoint_events
    assert checkpoint_events[-1]["checkpoint_id"] == checkpoint["checkpoint_id"]
    assert "current_goal" not in checkpoint_events[-1]


def test_resume_prompt_uses_checkpoint_state_not_just_history(tmp_path):
    agent = build_agent(tmp_path, ["<final>checkpoint ready.</final>"])
    agent.session["checkpoints"] = {
        "current_id": "ckpt_manual",
        "items": {
            "ckpt_manual": {
                "checkpoint_id": "ckpt_manual",
                "parent_checkpoint_id": "",
                "schema_version": "phase1-v1",
                "created_at": "2026-04-14T09:00:00+00:00",
                "current_goal": "Fix failing resume flow",
                "completed": ["Read runtime.py"],
                "excluded": ["Do not add branch summary"],
                "current_blocker": "Need to re-anchor stale file facts",
                "next_step": "Re-read runtime.py and refresh the checkpoint",
                "key_files": [{"path": "runtime.py", "freshness": "abc"}],
                "freshness": {"runtime.py": "abc"},
                "summary": "Resume from the latest checkpoint",
                "runtime_identity": {"workspace_fingerprint": "old-fingerprint"},
            }
        },
    }
    agent.session_store.save(agent.session)

    resumed = RepoHarness.from_session(
        model_client=FakeModelClient(["<final>Resumed.</final>"]),
        workspace=build_workspace(tmp_path),
        session_store=agent.session_store,
        session_id=agent.session["id"],
        approval_policy="auto",
    )

    assert resumed.ask("Continue the task") == "Resumed."

    prompt = resumed.model_client.prompts[-1]
    assert "Task checkpoint:" in prompt
    assert "Current goal: Fix failing resume flow" in prompt
    assert "Current blocker: Need to re-anchor stale file facts" in prompt
    assert "Next step: Re-read runtime.py and refresh the checkpoint" in prompt


def test_resume_invalidates_stale_file_summaries_and_marks_partial_stale(tmp_path):
    file_path = tmp_path / "runtime.py"
    file_path.write_text("alpha\n", encoding="utf-8")
    agent = build_agent(tmp_path, ["<final>checkpoint ready.</final>"])
    agent.memory.set_file_summary("runtime.py", "runtime.py: alpha")
    freshness = agent.memory.to_dict()["file_summaries"]["runtime.py"]["freshness"]
    agent.session["checkpoints"] = {
        "current_id": "ckpt_stale",
        "items": {
            "ckpt_stale": {
                "checkpoint_id": "ckpt_stale",
                "parent_checkpoint_id": "",
                "schema_version": "phase1-v1",
                "created_at": "2026-04-14T09:00:00+00:00",
                "current_goal": "Fix stale summary handling",
                "completed": [],
                "excluded": [],
                "current_blocker": "",
                "next_step": "Re-read runtime.py",
                "key_files": [{"path": "runtime.py", "freshness": freshness}],
                "freshness": {"runtime.py": freshness},
                "summary": "runtime.py is important",
                "runtime_identity": {"workspace_fingerprint": agent.workspace.fingerprint()},
            }
        },
    }
    agent.session_store.save(agent.session)
    file_path.write_text("beta\n", encoding="utf-8")

    resumed = RepoHarness.from_session(
        model_client=FakeModelClient(["<final>Resumed.</final>"]),
        workspace=build_workspace(tmp_path),
        session_store=agent.session_store,
        session_id=agent.session["id"],
        approval_policy="auto",
    )

    assert resumed.ask("Continue the task") == "Resumed."

    assert "runtime.py" not in resumed.memory.to_dict()["file_summaries"]
    assert resumed.last_prompt_metadata["resume_status"] == "partial-stale"
    assert resumed.last_prompt_metadata["stale_summary_invalidations"] == 1


def test_run_shell_nonzero_with_workspace_change_is_recorded_as_partial_success(tmp_path):
    agent = build_agent(tmp_path, [])

    result = agent.run_tool(
        "run_shell",
        {
            "command": "printf 'changed\\n' > README.md && exit 1",
            "timeout": 20,
        },
    )

    assert "exit_code: 1" in result
    assert agent._last_tool_result_metadata["tool_status"] == "partial_success"
    assert agent._last_tool_result_metadata["affected_paths"] == ["README.md"]
    assert agent._last_tool_result_metadata["workspace_changed"] is True


def test_shell_env_keeps_windows_required_variables(tmp_path):
    agent = build_agent(tmp_path, [], shell_env_allowlist=("PATH",))

    with patch.dict(
        os.environ,
        {
            "PATH": "C:\\Windows\\System32",
            "ComSpec": "C:\\Windows\\System32\\cmd.exe",
            "SystemRoot": "C:\\Windows",
            "PATHEXT": ".COM;.EXE;.BAT;.CMD",
            "USERPROFILE": "D:\\Profiles\\TestUser",
            "APPDATA": "D:\\Profiles\\TestUser\\AppData\\Roaming",
            "LOCALAPPDATA": "D:\\Profiles\\TestUser\\AppData\\Local",
        },
        clear=True,
    ):
        env = agent.shell_env()

    assert env["PATH"] == "C:\\Windows\\System32"
    assert env["ComSpec"] == "C:\\Windows\\System32\\cmd.exe"
    assert env["SystemRoot"] == "C:\\Windows"
    assert env["PATHEXT"] == ".COM;.EXE;.BAT;.CMD"
    assert env["USERPROFILE"] == "D:\\Profiles\\TestUser"
    assert env["APPDATA"] == "D:\\Profiles\\TestUser\\AppData\\Roaming"
    assert env["LOCALAPPDATA"] == "D:\\Profiles\\TestUser\\AppData\\Local"
    assert env["PWD"] == str(agent.root)


def test_run_shell_prefers_posix_shell_when_available(tmp_path):
    agent = build_agent(tmp_path, [])
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return "exit_code: 0\nstdout:\nok\nstderr:\n(empty)"

    with patch("repo_harness.tools._preferred_shell_path", return_value="C:\\Program Files\\Git\\bin\\bash.exe"), patch(
        "repo_harness.tools._run_shell_subprocess",
        fake_run,
    ):
        result = agent.run_tool("run_shell", {"command": "printf 'ok\\n'", "timeout": 20})

    assert captured["command"] == ["C:\\Program Files\\Git\\bin\\bash.exe", "-lc", "printf 'ok\\n'"]
    assert captured["kwargs"]["cwd"] == agent.root
    assert captured["kwargs"]["timeout"] == 20
    assert captured["kwargs"]["env"]["PWD"] == str(agent.root)
    assert captured["kwargs"]["shell"] is False
    assert "exit_code: 0" in result
    assert "ok" in result


def test_run_shell_falls_back_to_platform_shell_without_posix_shell(tmp_path):
    agent = build_agent(tmp_path, [])
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return "exit_code: 0\nstdout:\nplatform\nstderr:\n(empty)"

    with patch("repo_harness.tools._preferred_shell_path", return_value=""), patch(
        "repo_harness.tools._run_shell_subprocess",
        fake_run,
    ):
        result = agent.run_tool("run_shell", {"command": "echo platform", "timeout": 20})

    assert captured["command"] == "echo platform"
    assert captured["kwargs"]["shell"] is True
    assert captured["kwargs"]["cwd"] == agent.root
    assert captured["kwargs"]["timeout"] == 20
    assert captured["kwargs"]["env"]["PWD"] == str(agent.root)
    assert "exit_code: 0" in result
    assert "platform" in result


def test_resume_marks_workspace_mismatch_when_checkpoint_runtime_identity_is_stale(tmp_path):
    agent = build_agent(tmp_path, ["<final>checkpoint ready.</final>"])
    agent.session["checkpoints"] = {
        "current_id": "ckpt_workspace",
        "items": {
            "ckpt_workspace": {
                "checkpoint_id": "ckpt_workspace",
                "parent_checkpoint_id": "",
                "schema_version": "phase1-v1",
                "created_at": "2026-04-14T09:00:00+00:00",
                "current_goal": "Continue after drift",
                "completed": [],
                "excluded": [],
                "current_blocker": "",
                "next_step": "Rebuild runtime state",
                "key_files": [],
                "freshness": {},
                "summary": "workspace changed",
                "runtime_identity": {"workspace_fingerprint": "outdated-fingerprint"},
            }
        },
    }
    agent.session_store.save(agent.session)

    resumed = RepoHarness.from_session(
        model_client=FakeModelClient(["<final>Resumed.</final>"]),
        workspace=build_workspace(tmp_path),
        session_store=agent.session_store,
        session_id=agent.session["id"],
        approval_policy="auto",
    )

    assert resumed.ask("Continue the task") == "Resumed."
    assert resumed.last_prompt_metadata["resume_status"] == "workspace-mismatch"


def test_write_file_trace_records_minimum_tool_contract_fields(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            '<tool>{"name":"write_file","args":{"path":"notes.txt","content":"hello\\n"}}</tool>',
            "<final>Done.</final>",
        ],
    )

    assert agent.ask("Create notes.txt") == "Done."

    trace_events = [
        json.loads(line)
        for line in agent.run_store.trace_path(agent.current_task_state).read_text(encoding="utf-8").splitlines()
    ]
    tool_event = [event for event in trace_events if event["event"] == "tool_executed"][-1]

    assert tool_event["name"] == "write_file"
    assert tool_event["risk_level"] == "high"
    assert tool_event["read_only"] is False
    assert tool_event["tool_status"] == "ok"
    assert tool_event["affected_paths"] == ["notes.txt"]
    assert tool_event["workspace_changed"] is True
    assert tool_event["diff_summary"] == ["created:notes.txt"]


def test_resume_marks_schema_mismatch_when_checkpoint_version_is_incompatible(tmp_path):
    agent = build_agent(tmp_path, ["<final>checkpoint ready.</final>"])
    agent.session["checkpoints"] = {
        "current_id": "ckpt_schema",
        "items": {
            "ckpt_schema": {
                "checkpoint_id": "ckpt_schema",
                "parent_checkpoint_id": "",
                "schema_version": "legacy-v0",
                "created_at": "2026-04-14T09:00:00+00:00",
                "current_goal": "Continue after schema change",
                "completed": [],
                "excluded": [],
                "current_blocker": "",
                "next_step": "Migrate checkpoint",
                "key_files": [],
                "freshness": {},
                "summary": "schema changed",
                "runtime_identity": {"workspace_fingerprint": agent.workspace.fingerprint()},
            }
        },
    }
    agent.session_store.save(agent.session)

    resumed = RepoHarness.from_session(
        model_client=FakeModelClient(["<final>Resumed.</final>"]),
        workspace=build_workspace(tmp_path),
        session_store=agent.session_store,
        session_id=agent.session["id"],
        approval_policy="auto",
    )

    assert resumed.ask("Continue the task") == "Resumed."
    assert resumed.last_prompt_metadata["resume_status"] == "schema-mismatch"


def test_resume_marks_no_checkpoint_when_session_has_no_checkpoint_state(tmp_path):
    agent = build_agent(tmp_path, ["<final>checkpoint ready.</final>"])
    agent.session.pop("checkpoints", None)
    agent.session_store.save(agent.session)

    resumed = RepoHarness.from_session(
        model_client=FakeModelClient(["<final>Resumed.</final>"]),
        workspace=build_workspace(tmp_path),
        session_store=agent.session_store,
        session_id=agent.session["id"],
        approval_policy="auto",
    )

    assert resumed.ask("Continue the task") == "Resumed."
    assert resumed.last_prompt_metadata["resume_status"] == "no-checkpoint"
    assert "Task checkpoint:" not in resumed.model_client.prompts[-1]


def test_freshness_mismatch_creates_checkpoint_before_model_completion(tmp_path):
    file_path = tmp_path / "runtime.py"
    file_path.write_text("alpha\n", encoding="utf-8")
    agent = build_agent(tmp_path, ["<final>Resumed.</final>"])
    agent.memory.set_file_summary("runtime.py", "runtime.py: alpha")
    freshness = agent.memory.to_dict()["file_summaries"]["runtime.py"]["freshness"]
    agent.session["checkpoints"] = {
        "current_id": "ckpt_freshness",
        "items": {
            "ckpt_freshness": {
                "checkpoint_id": "ckpt_freshness",
                "parent_checkpoint_id": "",
                "schema_version": "phase1-v1",
                "created_at": "2026-04-14T09:00:00+00:00",
                "current_goal": "Handle freshness mismatch",
                "completed": [],
                "excluded": [],
                "current_blocker": "",
                "next_step": "Re-read runtime.py",
                "key_files": [{"path": "runtime.py", "freshness": freshness}],
                "freshness": {"runtime.py": freshness},
                "summary": "runtime.py changed",
                "runtime_identity": {"workspace_fingerprint": agent.workspace.fingerprint()},
            }
        },
    }
    agent.session_store.save(agent.session)
    file_path.write_text("beta\n", encoding="utf-8")

    assert agent.ask("Continue the task") == "Resumed."

    trace_events = [
        json.loads(line)
        for line in agent.run_store.trace_path(agent.current_task_state).read_text(encoding="utf-8").splitlines()
    ]
    checkpoint_events = [event for event in trace_events if event["event"] == "checkpoint_created"]

    assert checkpoint_events
    assert checkpoint_events[0]["trigger"] == "freshness_mismatch"


def test_runtime_identity_persists_key_execution_metadata(tmp_path):
    workspace = build_workspace(tmp_path)
    store = SessionStore(tmp_path / ".repo-harness" / "sessions")
    agent = RepoHarness(
        model_client=FakeModelClient(["<final>Done.</final>"]),
        workspace=workspace,
        session_store=store,
        approval_policy="never",
        max_steps=9,
        max_new_tokens=1024,
        feature_flags={"memory": True, "relevant_memory": False},
    )

    runtime_identity = agent.session["runtime_identity"]

    assert runtime_identity["session_id"] == agent.session["id"]
    assert runtime_identity["cwd"] == str(tmp_path)
    assert runtime_identity["approval_policy"] == "never"
    assert runtime_identity["read_only"] is False
    assert runtime_identity["max_steps"] == 9
    assert runtime_identity["max_new_tokens"] == 1024
    assert runtime_identity["feature_flags"]["memory"] is True
    assert runtime_identity["feature_flags"]["relevant_memory"] is False
    assert runtime_identity["shell_env_allowlist"] == list(agent.shell_env_allowlist)


def test_resume_records_runtime_identity_mismatch_fields_in_metadata_and_trace(tmp_path):
    agent = build_agent(tmp_path, ["<final>checkpoint ready.</final>"])
    agent.session["checkpoints"] = {
        "current_id": "ckpt_identity",
        "items": {
            "ckpt_identity": {
                "checkpoint_id": "ckpt_identity",
                "parent_checkpoint_id": "",
                "schema_version": "phase1-v1",
                "created_at": "2026-04-14T09:00:00+00:00",
                "current_goal": "Resume with a different runtime identity",
                "completed": [],
                "excluded": [],
                "current_blocker": "",
                "next_step": "Rebuild runtime identity",
                "key_files": [],
                "freshness": {},
                "summary": "identity changed",
                "runtime_identity": {
                    "workspace_fingerprint": agent.workspace.fingerprint(),
                    "approval_policy": "auto",
                    "read_only": False,
                    "max_steps": 6,
                    "max_new_tokens": 512,
                    "model": "old-model",
                    "model_client": "FakeModelClient",
                    "feature_flags": {"memory": True, "relevant_memory": True},
                    "shell_env_allowlist": ["PATH"],
                    "session_id": agent.session["id"],
                    "cwd": str(tmp_path),
                },
            }
        },
    }
    agent.session_store.save(agent.session)

    resumed = RepoHarness.from_session(
        model_client=FakeModelClient(["<final>Resumed.</final>"]),
        workspace=build_workspace(tmp_path),
        session_store=agent.session_store,
        session_id=agent.session["id"],
        approval_policy="never",
        max_steps=9,
        max_new_tokens=1024,
        feature_flags={"memory": True, "relevant_memory": False},
    )

    resumed.ask("Continue the task")

    assert resumed.last_prompt_metadata["resume_status"] == "workspace-mismatch"
    assert resumed.last_prompt_metadata["runtime_identity_mismatch_fields"] == [
        "approval_policy",
        "feature_flags",
        "max_new_tokens",
        "max_steps",
        "model",
        "shell_env_allowlist",
    ]

    trace_events = [
        json.loads(line)
        for line in resumed.run_store.trace_path(resumed.current_task_state).read_text(encoding="utf-8").splitlines()
    ]
    mismatch_events = [event for event in trace_events if event["event"] == "runtime_identity_mismatch"]
    assert mismatch_events
    assert mismatch_events[0]["fields"] == [
        "approval_policy",
        "feature_flags",
        "max_new_tokens",
        "max_steps",
        "model",
        "shell_env_allowlist",
    ]


def test_partial_success_creates_process_note_for_exploration_history(tmp_path):
    agent = build_agent(tmp_path, [])

    agent.run_tool(
        "run_shell",
        {
            "command": "printf 'changed\\n' > README.md && exit 1",
            "timeout": 20,
        },
    )

    process_notes = [
        note
        for note in agent.memory.to_dict()["episodic_notes"]
        if note.get("kind") == "process"
    ]

    assert process_notes
    assert process_notes[-1]["text"] == "run_shell partial_success on README.md; inspect diff before retry"
    assert "partial_success" in process_notes[-1]["tags"]
    assert "README.md" in process_notes[-1]["tags"]


def read_review_queue(workspace_root):
    queue_path = workspace_root / ".repo-harness" / "memory" / "review-queue.jsonl"
    if not queue_path.exists():
        return []
    return [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_explicit_memory_promotion_queues_durable_memory_review_candidates(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            "<final>Project convention: Use constrained tools instead of guessing.\n"
            "Project convention: Preserve local agent state under .repo-harness/.\n"
            "Decision: Keep durable memory topic-based and lightweight.</final>",
        ],
    )

    answer = agent.ask(
        "Capture the stable facts you already discovered as durable memory. "
        "Respond with exactly the long-term facts."
    )

    assert "Project convention:" in answer

    index_path = tmp_path / ".repo-harness" / "memory" / "MEMORY.md"
    conventions_path = tmp_path / ".repo-harness" / "memory" / "topics" / "project-conventions.md"
    decisions_path = tmp_path / ".repo-harness" / "memory" / "topics" / "key-decisions.md"
    report = json.loads(agent.run_store.report_path(agent.current_task_state).read_text(encoding="utf-8"))
    queue = read_review_queue(tmp_path)

    assert not index_path.exists()
    assert not conventions_path.exists()
    assert not decisions_path.exists()
    assert [record["schema_version"] for record in queue] == ["durable-review-queue-v1"] * 3
    assert [record["status"] for record in queue] == ["pending", "pending", "pending"]
    assert [f"{record['topic']}: {record['text']}" for record in queue] == [
        "project-conventions: Use constrained tools instead of guessing.",
        "project-conventions: Preserve local agent state under .repo-harness/.",
        "key-decisions: Keep durable memory topic-based and lightweight.",
    ]
    assert all(isinstance(record["source"], dict) and record["source"].get("run_id") for record in queue)
    assert report["durable_promotions"] == []
    assert report["durable_review_queued"] == [
        "project-conventions: Use constrained tools instead of guessing.",
        "project-conventions: Preserve local agent state under .repo-harness/.",
        "key-decisions: Keep durable memory topic-based and lightweight.",
    ]


def test_explicit_memory_promotion_supports_chinese_intent_and_labels(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            "<final>项目约定：优先使用受约束工具，不要靠猜。\n"
            "决策：持久记忆保持轻量、按 topic 管理。</final>",
        ],
    )

    answer = agent.ask("请把下面这些稳定事实记住，作为长期记忆保存下来。")

    assert "项目约定：" in answer

    queue = read_review_queue(tmp_path)

    assert [f"{record['topic']}: {record['text']}" for record in queue] == [
        "project-conventions: 优先使用受约束工具，不要靠猜。",
        "key-decisions: 持久记忆保持轻量、按 topic 管理。",
    ]
    assert not (tmp_path / ".repo-harness" / "memory" / "topics").exists()


def test_explicit_memory_promotion_rejects_secret_shaped_and_transient_lines(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            "<final>Project convention: Use constrained tools instead of guessing.\n"
            "Dependency: API key is sk-live-secret-abc.\n"
            "Decision: Current goal is fix flaky tests.\n"
            "Dependency: stdout: FAIL test_one FAIL test_two FAIL test_three.</final>",
        ],
    )

    agent.ask("Capture these stable facts into durable memory.")

    report = json.loads(agent.run_store.report_path(agent.current_task_state).read_text(encoding="utf-8"))
    dependency_path = tmp_path / ".repo-harness" / "memory" / "topics" / "dependency-facts.md"
    queue = read_review_queue(tmp_path)

    assert report["durable_promotions"] == []
    assert report["durable_review_queued"] == [
        "project-conventions: Use constrained tools instead of guessing.",
    ]
    assert report["durable_rejections"] == [
        "dependency-facts:secret_shaped",
        "key-decisions:transient_task_state",
        "dependency-facts:noisy_output",
    ]
    assert [record["text"] for record in queue] == ["Use constrained tools instead of guessing."]
    assert "sk-live-secret" not in json.dumps(queue)
    assert "Current goal" not in json.dumps(queue)
    assert "stdout" not in json.dumps(queue)
    assert not dependency_path.exists()


def test_memory_self_iteration_compacts_notes_and_queues_review_candidates(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            "<final>Done.</final>",
        ],
    )
    for index in range(11):
        agent.memory.append_note(f"old task observation {index}", tags=("task",), source="test")
    agent.memory.append_note(
        "Project convention: Use explicit memory review before durable writes.",
        tags=("stable",),
        source="test",
    )
    agent.session["memory"] = agent.memory.to_dict()

    assert agent.ask("Continue the task") == "Done."

    memory_state = agent.memory.to_dict()
    compacted_notes = [
        note
        for note in memory_state["episodic_notes"]
        if note.get("source") == "episodic-compaction"
    ]
    conventions_path = tmp_path / ".repo-harness" / "memory" / "topics" / "project-conventions.md"
    pending = read_review_queue(tmp_path)
    report = json.loads(agent.run_store.report_path(agent.current_task_state).read_text(encoding="utf-8"))

    assert compacted_notes
    assert compacted_notes[0]["text"].startswith("Compacted earlier notes:")
    assert not conventions_path.exists()
    assert pending[0]["topic"] == "project-conventions"
    assert pending[0]["text"] == "Use explicit memory review before durable writes."
    assert pending[0]["source"]["origin"] == "memory-self-iteration"
    assert report["episodic_compactions"] == [compacted_notes[0]["text"]]
    assert report["self_iteration_review_queued"] == [
        "project-conventions: Use explicit memory review before durable writes."
    ]
    assert report["self_iteration_rejections"] == []
    assert report["durable_promotions"] == []


def test_memory_self_iteration_filters_secret_candidates(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            "<final>Done.</final>",
        ],
    )
    for index in range(11):
        agent.memory.append_note(f"old task observation {index}", tags=("task",), source="test")
    agent.memory.append_note(
        "Dependency: API key is sk-self-iteration-secret.",
        tags=("stable",),
        source="test",
    )
    agent.session["memory"] = agent.memory.to_dict()

    assert agent.ask("Continue the task") == "Done."

    report = json.loads(agent.run_store.report_path(agent.current_task_state).read_text(encoding="utf-8"))
    assert read_review_queue(tmp_path) == []
    assert report["self_iteration_review_queued"] == []
    assert report["self_iteration_rejections"] == ["dependency-facts:secret_shaped"]
    assert not (tmp_path / ".repo-harness" / "memory" / "topics" / "dependency-facts.md").exists()


def test_memory_self_iteration_does_not_requeue_accepted_or_rejected_candidates(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            "<final>First pass.</final>",
            "<final>Second pass.</final>",
            "<final>Third pass.</final>",
        ],
    )
    for index in range(10):
        agent.memory.append_note(f"old task observation {index}", tags=("task",), source="test")
    agent.memory.append_note(
        "Project convention: Use explicit memory review before durable writes.",
        tags=("stable",),
        source="test",
    )
    agent.memory.append_note(
        "Preference: Keep explanations concise.",
        tags=("stable",),
        source="test",
    )
    agent.session["memory"] = agent.memory.to_dict()

    assert agent.ask("Continue the task") == "First pass."
    pending = read_review_queue(tmp_path)
    accepted = next(record for record in pending if record["topic"] == "project-conventions")
    rejected = next(record for record in pending if record["topic"] == "user-preferences")

    agent.memory_review_accept(accepted["id"])
    agent.memory_review_reject(rejected["id"])

    assert agent.ask("Continue the task again") == "Second pass."
    assert agent.ask("Continue the task once more") == "Third pass."

    queue = read_review_queue(tmp_path)
    assert [
        (record["topic"], record["text"], record["status"])
        for record in queue
        if record.get("source", {}).get("origin") == "memory-self-iteration"
    ] == [
        ("project-conventions", "Use explicit memory review before durable writes.", "accepted"),
        ("user-preferences", "Keep explanations concise.", "rejected"),
    ]
    latest_report = json.loads(agent.run_store.report_path(agent.current_task_state).read_text(encoding="utf-8"))
    assert latest_report["self_iteration_review_queued"] == []


def test_memory_self_iteration_does_not_requeue_edit_accepted_candidate(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            "<final>First pass.</final>",
            "<final>Second pass.</final>",
        ],
    )
    for index in range(11):
        agent.memory.append_note(f"old task observation {index}", tags=("task",), source="test")
    agent.memory.append_note(
        "Project convention: Use explicit memory review before durable writes.",
        tags=("stable",),
        source="test",
    )
    agent.session["memory"] = agent.memory.to_dict()

    assert agent.ask("Continue the task") == "First pass."
    pending = read_review_queue(tmp_path)
    result = agent.memory_review_edit(
        pending[0]["id"],
        topic="project-conventions",
        text="Use explicit review before writing durable memory.",
    )

    assert result["status"] == "accepted"
    assert agent.ask("Continue the task again") == "Second pass."

    queue = read_review_queue(tmp_path)
    assert [
        (record["text"], record["status"])
        for record in queue
        if record.get("source", {}).get("origin") == "memory-self-iteration"
    ] == [
        ("Use explicit review before writing durable memory.", "accepted"),
    ]
    latest_report = json.loads(agent.run_store.report_path(agent.current_task_state).read_text(encoding="utf-8"))
    assert latest_report["self_iteration_review_queued"] == []


def test_memory_self_iteration_skips_existing_durable_equivalent_fact(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            "<final>First pass.</final>",
            "<final>Second pass.</final>",
        ],
    )
    agent.memory.promote_durable(
        [("project-conventions", "Use memory pack for safe transfer.")]
    )
    for index in range(11):
        agent.memory.append_note(f"old task observation {index}", tags=("task",), source="test")
    agent.memory.append_note(
        "Project convention: use memory-pack for safe transfer",
        tags=("stable",),
        source="test",
    )
    agent.session["memory"] = agent.memory.to_dict()

    assert agent.ask("Continue the task") == "First pass."
    assert agent.ask("Continue the task again") == "Second pass."

    assert read_review_queue(tmp_path) == []
    latest_report = json.loads(agent.run_store.report_path(agent.current_task_state).read_text(encoding="utf-8"))
    assert latest_report["self_iteration_review_queued"] == []


def test_explicit_memory_promotion_supersedes_matching_durable_fact(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            "<final>Dependency: Python runtime is 3.11.</final>",
            "<final>Dependency: Python runtime is 3.12.</final>",
        ],
    )

    assert agent.ask("Capture this stable dependency fact into durable memory.") == "Dependency: Python runtime is 3.11."
    first_result = agent.memory_review_accept(read_review_queue(tmp_path)[0]["id"])

    assert agent.ask("Save the updated dependency fact into durable memory.") == "Dependency: Python runtime is 3.12."
    second_result = agent.memory_review_accept(agent.memory_review_pending()[0]["id"])

    dependency_path = tmp_path / ".repo-harness" / "memory" / "topics" / "dependency-facts.md"
    text = dependency_path.read_text(encoding="utf-8")

    assert first_result["promoted"] == ["dependency-facts: Python runtime is 3.11."]
    assert "Python runtime is 3.12." in text
    assert "Python runtime is 3.11." not in text
    assert second_result["superseded"] == [
        "dependency-facts: Python runtime is 3.11. -> Python runtime is 3.12.",
    ]


def test_explicit_memory_promotion_dedupes_duplicate_durable_note(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            "<final>Project convention: Use constrained tools instead of guessing.</final>",
            "<final>Project convention: Use constrained tools instead of guessing.</final>",
        ],
    )

    agent.ask("Capture the stable fact into durable memory.")
    agent.memory_review_accept(read_review_queue(tmp_path)[0]["id"])
    agent.ask("Capture the stable fact into durable memory again.")
    agent.memory_review_accept(agent.memory_review_pending()[0]["id"])

    conventions_path = tmp_path / ".repo-harness" / "memory" / "topics" / "project-conventions.md"
    text = conventions_path.read_text(encoding="utf-8")

    assert text.count("Use constrained tools instead of guessing.") == 1


def test_memory_review_accept_edit_reject_and_skip_control_durable_writes(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            "<final>Project convention: Use constrained tools.\n"
            "Decision: Python runtime is 3.11.\n"
            "Dependency: Package manager is uv.\n"
            "Preference: Keep explanations concise.</final>",
        ],
    )

    agent.ask("Capture these stable facts into durable memory.")
    pending = agent.memory_review_pending()

    accept_result = agent.memory_review_accept(pending[0]["id"])
    edit_result = agent.memory_review_edit(
        pending[1]["id"],
        topic="dependency-facts",
        text="Python runtime is 3.12.",
    )
    reject_result = agent.memory_review_reject(pending[2]["id"])
    skip_result = agent.memory_review_skip(pending[3]["id"])

    conventions_path = tmp_path / ".repo-harness" / "memory" / "topics" / "project-conventions.md"
    dependency_path = tmp_path / ".repo-harness" / "memory" / "topics" / "dependency-facts.md"
    queue = read_review_queue(tmp_path)

    assert accept_result["promoted"] == ["project-conventions: Use constrained tools."]
    assert edit_result["promoted"] == ["dependency-facts: Python runtime is 3.12."]
    assert reject_result["status"] == "rejected"
    assert skip_result["status"] == "pending"
    assert "Use constrained tools." in conventions_path.read_text(encoding="utf-8")
    dependency_text = dependency_path.read_text(encoding="utf-8")
    assert "Python runtime is 3.12." in dependency_text
    assert "Python runtime is 3.11." not in dependency_text
    assert "Package manager is uv." not in dependency_text
    assert agent.memory_review_pending()[0]["text"] == "Keep explanations concise."
    assert [record["status"] for record in queue] == ["accepted", "accepted", "rejected", "pending"]


def test_memory_review_edit_rejects_secret_shaped_and_transient_text(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            "<final>Project convention: Use constrained tools.\n"
            "Dependency: Python runtime is 3.11.</final>",
        ],
    )

    agent.ask("Capture these stable facts into durable memory.")
    pending = agent.memory_review_pending()

    secret_result = agent.memory_review_edit(
        pending[0]["id"],
        topic="dependency-facts",
        text="API key is sk-review-secret.",
    )
    transient_result = agent.memory_review_edit(
        pending[1]["id"],
        topic="key-decisions",
        text="Current goal is debug review queue.",
    )

    queue = read_review_queue(tmp_path)
    dependency_path = tmp_path / ".repo-harness" / "memory" / "topics" / "dependency-facts.md"

    assert secret_result["status"] == "rejected"
    assert secret_result["reason"] == "secret_shaped"
    assert transient_result["status"] == "rejected"
    assert transient_result["reason"] == "transient_task_state"
    assert [record["status"] for record in queue] == ["pending", "pending"]
    assert not dependency_path.exists()


def test_agent_records_model_cache_metadata_in_last_prompt_metadata(tmp_path):
    class CacheAwareFakeModelClient(FakeModelClient):
        def complete(self, prompt, max_new_tokens, **kwargs):
            self.last_completion_metadata = {
                "prompt_cache_supported": True,
                "cached_tokens": 512,
                "cache_hit": True,
                "input_tokens": 1024,
            }
            return super().complete(prompt, max_new_tokens, **kwargs)

    workspace = build_workspace(tmp_path)
    store = SessionStore(tmp_path / ".repo-harness" / "sessions")
    agent = RepoHarness(
        model_client=CacheAwareFakeModelClient(["<final>Done.</final>"]),
        workspace=workspace,
        session_store=store,
        approval_policy="auto",
    )

    assert agent.ask("Cache aware run") == "Done."

    assert agent.last_prompt_metadata["prompt_cache_supported"] is True
    assert agent.last_prompt_metadata["cached_tokens"] == 512
    assert agent.last_prompt_metadata["cache_hit"] is True
    assert agent.last_prompt_metadata["prefix_hash"]
    assert agent.last_prompt_metadata["prompt_cache_key"] == agent.last_prompt_metadata["prefix_hash"]


def test_recent_transcript_entries_stay_richer_than_older_ones(tmp_path):
    agent = build_agent(tmp_path, ["<final>Done.</final>"])
    old_text = "OLD-" + ("A" * 320)
    recent_text = "RECENT-" + ("B" * 320)

    agent.record({"role": "user", "content": old_text, "created_at": "2026-04-07T09:00:00+00:00"})
    agent.record({"role": "assistant", "content": old_text, "created_at": "2026-04-07T09:01:00+00:00"})
    agent.record({"role": "user", "content": recent_text, "created_at": "2026-04-07T09:02:00+00:00"})
    agent.record({"role": "assistant", "content": recent_text, "created_at": "2026-04-07T09:03:00+00:00"})
    agent.record({"role": "user", "content": recent_text, "created_at": "2026-04-07T09:04:00+00:00"})
    agent.record({"role": "assistant", "content": recent_text, "created_at": "2026-04-07T09:05:00+00:00"})
    agent.record({"role": "user", "content": recent_text, "created_at": "2026-04-07T09:06:00+00:00"})
    agent.record({"role": "assistant", "content": recent_text, "created_at": "2026-04-07T09:07:00+00:00"})

    assert agent.ask("Check the transcript") == "Done."

    prompt = agent.model_client.prompts[-1]

    assert recent_text in prompt
    assert old_text not in prompt


def test_public_api_exports_resolve_through_package_path():
    assert callable(build_welcome)
    assert FakeModelClient is not None
    assert RepoHarness is not None
    assert OllamaModelClient is not None
    assert SessionStore is not None
    assert WorkspaceContext is not None
    assert Path(harness_pkg.__file__).as_posix().endswith("/repo_harness/__init__.py")


def test_reviewer_skeleton_docs_exist():
    review_pack = Path("docs/review-pack/README.md")
    architecture = Path("docs/architecture/agent-harness-v1-overview.md")

    assert review_pack.exists()
    assert architecture.exists()

    review_text = review_pack.read_text(encoding="utf-8")
    assert "Project pitch" in review_text
    assert "Architecture map" in review_text
    assert "Benchmark evidence" in review_text
    assert "Sample run artifact list" in review_text

    architecture_text = architecture.read_text(encoding="utf-8")
    assert "Agent Harness v1" in architecture_text
    assert "task state" in architecture_text.lower()


def test_getting_started_guide_is_linked_and_covers_onboarding_basics():
    guide = Path("docs/getting-started.md")
    readme = Path("README.md")

    assert guide.exists()
    assert "docs/getting-started.md" in readme.read_text(encoding="utf-8")

    guide_text = guide.read_text(encoding="utf-8")
    for required in [
        "PowerShell",
        "CMD",
        "Ollama",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "/help",
        ".repo-harness/runs",
        "v2.0 历史实验结果",
        "AI 产品经理",
    ]:
        assert required in guide_text


class DummyCliAgent:
    def __init__(self, tmp_path):
        self.workspace = type("Workspace", (), {"cwd": str(tmp_path), "branch": "main"})()
        self.model_client = type("Model", (), {"model": "test-model", "host": "http://test"})()
        self.approval_policy = "auto"
        self.session = {"id": "dummy-session"}
        self.session_path = str(tmp_path / ".repo-harness" / "sessions" / "dummy-session.json")

    def ask(self, prompt):
        raise AssertionError(f"memory command was routed to agent.ask: {prompt}")

    def memory_text(self):
        return "Memory:\n- task: -"

    def memory_explain_text(self, query):
        return f"Memory explanation for: {query}\n- score=3 kind=durable source=project-conventions text=Use constrained tools instead of guessing."

    def memory_self_iteration_text(self):
        return (
            "Memory self-iteration:\n"
            "- last compactions: 1\n"
            "- queued candidates: 1\n"
            "- rejections: 0\n"
            "- pending review candidates: 1\n"
            "Use /memory review to accept, edit, reject, or skip pending durable memory candidates."
        )

    def reset(self):
        raise AssertionError("memory command should not reset the session")


def write_cli_durable_memory(workspace_root):
    memory_root = workspace_root / ".repo-harness" / "memory"
    topics_dir = memory_root / "topics"
    topics_dir.mkdir(parents=True)
    (memory_root / "MEMORY.md").write_text(
        "# Durable Memory Index\n\n"
        "- [project-conventions](topics/project-conventions.md): Project Conventions\n"
        "  - summary: Stable repository conventions.\n"
        "  - tags: convention\n",
        encoding="utf-8",
    )
    (topics_dir / "project-conventions.md").write_text(
        "# Project Conventions\n\n"
        "- topic: project-conventions\n"
        "- summary: Stable repository conventions.\n"
        "- tags: convention\n"
        "- updated_at: 2026-05-05T00:00:00+00:00\n\n"
        "## Notes\n"
        "- Use constrained tools instead of guessing.\n",
        encoding="utf-8",
    )


def test_cli_memory_export_uses_requested_preset_without_model(tmp_path, capsys):
    write_cli_durable_memory(tmp_path)
    pack_path = tmp_path / "memory-pack.zip"
    with patch("repo_harness.cli.build_agent", return_value=DummyCliAgent(tmp_path)) as build_agent, patch(
        "repo_harness.cli.build_welcome",
        return_value="welcome",
    ):
        result = mini_cli.main(
            [
                "memory",
                "export",
                "--cwd",
                str(tmp_path),
                "--preset",
                "safe-transfer",
                "--output",
                str(pack_path),
            ]
        )

    assert result == 0
    build_agent.assert_not_called()
    output = capsys.readouterr().out
    assert str(pack_path) in output
    assert "preset: safe-transfer" in output
    with zipfile.ZipFile(pack_path) as archive:
        manifest = json.loads(archive.read("repo-harness-memory-pack.json").decode("utf-8"))
    assert manifest["preset"] == "safe-transfer"
    assert manifest["modules"] == ["durable_knowledge"]


def test_cli_memory_inspect_and_validate_use_public_api_without_model(tmp_path, capsys):
    from repo_harness import memory_pack

    write_cli_durable_memory(tmp_path)
    pack_path = tmp_path / "memory-pack.zip"
    memory_pack.export_memory_pack(tmp_path, output_path=pack_path, preset="safe-transfer")

    with patch("repo_harness.cli.build_agent", return_value=DummyCliAgent(tmp_path)) as build_agent, patch(
        "repo_harness.cli.build_welcome",
        return_value="welcome",
    ):
        inspect_result = mini_cli.main(["memory", "inspect", str(pack_path)])

    assert inspect_result == 0
    build_agent.assert_not_called()
    inspect_output = capsys.readouterr().out
    assert "safe-transfer" in inspect_output
    assert "durable_knowledge" in inspect_output

    with patch("repo_harness.cli.build_agent", return_value=DummyCliAgent(tmp_path)) as build_agent, patch(
        "repo_harness.cli.build_welcome",
        return_value="welcome",
    ):
        validate_result = mini_cli.main(["memory", "validate", str(pack_path)])

    assert validate_result == 0
    build_agent.assert_not_called()
    assert "valid" in capsys.readouterr().out.lower()


def test_cli_memory_relative_pack_paths_resolve_against_cwd(tmp_path, capsys):
    from repo_harness import memory_pack

    write_cli_durable_memory(tmp_path)
    pack_path = tmp_path / "memory-pack.zip"
    memory_pack.export_memory_pack(tmp_path, output_path=pack_path, preset="safe-transfer")

    with patch("repo_harness.cli.build_agent", return_value=DummyCliAgent(tmp_path)) as build_agent:
        result = mini_cli.main(["memory", "inspect", "memory-pack.zip", "--cwd", str(tmp_path)])

    assert result == 0
    build_agent.assert_not_called()
    output = capsys.readouterr().out
    assert "safe-transfer" in output


def test_repl_help_mentions_memory_pack_menu():
    assert "/memory_pack" in mini_cli.HELP_DETAILS
    assert "memory packs" in mini_cli.HELP_DETAILS
    assert "/memory_explain <query>" in mini_cli.HELP_DETAILS
    assert "/memory review" in mini_cli.HELP_DETAILS
    assert "/memory self_iteration" in mini_cli.HELP_DETAILS


def test_repl_memory_pack_aliases_show_menu_without_model_call(tmp_path, capsys):
    with patch("repo_harness.cli.build_agent", return_value=DummyCliAgent(tmp_path)), patch(
        "builtins.input", side_effect=["/memory_pack", "0", "/memory-pack", "0", "/exit"]
    ), patch.dict("os.environ", {"NO_COLOR": "1"}, clear=False):
        result = mini_cli.main(["--cwd", str(tmp_path)])

    assert result == 0
    output = capsys.readouterr().out
    assert output.count("Memory Pack") >= 2 or output.count("memory pack") >= 2
    assert "safe-transfer" in output or "Safe transfer" in output
    assert "continue-work" in output or "Continue work" in output
    assert "full-recovery" in output or "Full recovery" in output


def test_repl_memory_explain_is_read_only_and_does_not_call_model(tmp_path, capsys):
    agent = DummyCliAgent(tmp_path)
    original_session = dict(agent.session)
    with patch("repo_harness.cli.build_agent", return_value=agent), patch(
        "repo_harness.cli.build_welcome",
        return_value="welcome",
    ), patch("builtins.input", side_effect=["/memory_explain conventions", "/memory_explain", "/exit"]):
        result = mini_cli.main(["--cwd", str(tmp_path)])

    assert result == 0
    assert agent.session == original_session
    output = capsys.readouterr().out
    assert "Memory explanation for: conventions" in output
    assert "score=3" in output
    assert "usage: /memory_explain <query>" in output


def test_repl_memory_self_iteration_is_read_only_and_does_not_call_model(tmp_path, capsys):
    agent = DummyCliAgent(tmp_path)
    original_session = dict(agent.session)
    with patch("repo_harness.cli.build_agent", return_value=agent), patch(
        "repo_harness.cli.build_welcome",
        return_value="welcome",
    ), patch("builtins.input", side_effect=["/memory self_iteration", "/exit"]):
        result = mini_cli.main(["--cwd", str(tmp_path)])

    assert result == 0
    assert agent.session == original_session
    output = capsys.readouterr().out
    assert "Memory self-iteration:" in output
    assert "queued candidates: 1" in output
    assert "Use /memory review" in output


def test_repl_final_answer_reports_self_iteration_review_candidates(tmp_path, capsys):
    agent = build_agent(
        tmp_path,
        [
            "<final>Done.</final>",
        ],
    )
    for index in range(11):
        agent.memory.append_note(f"old task observation {index}", tags=("task",), source="test")
    agent.memory.append_note(
        "Project convention: Use explicit memory review before durable writes.",
        tags=("stable",),
        source="test",
    )
    agent.session["memory"] = agent.memory.to_dict()

    with patch("repo_harness.cli.build_agent", return_value=agent), patch(
        "builtins.input", side_effect=["Continue the task", "/exit"]
    ), patch.dict("os.environ", {"NO_COLOR": "1"}, clear=False):
        result = mini_cli.main(["--cwd", str(tmp_path)])

    assert result == 0
    output = capsys.readouterr().out
    assert "Done." in output
    assert "memory self-iteration: queued 1 durable memory candidate for review" in output
    assert "run /memory review to accept, edit, reject, or skip" in output


def test_repl_memory_review_accepts_pending_candidate_without_model_call(tmp_path, capsys):
    agent = build_agent(
        tmp_path,
        [
            "<final>Project convention: Use constrained tools instead of guessing.</final>",
        ],
    )
    agent.ask("Capture the stable fact into durable memory.")

    with patch("repo_harness.cli.build_agent", return_value=agent), patch(
        "repo_harness.cli.build_welcome",
        return_value="welcome",
    ), patch("builtins.input", side_effect=["/memory review", "accept", "/exit"]):
        result = mini_cli.main(["--cwd", str(tmp_path)])

    assert result == 0
    output = capsys.readouterr().out
    assert "pending durable memory candidates" in output
    assert "accepted: project-conventions: Use constrained tools instead of guessing." in output
    conventions_path = tmp_path / ".repo-harness" / "memory" / "topics" / "project-conventions.md"
    assert "Use constrained tools instead of guessing." in conventions_path.read_text(encoding="utf-8")


def test_repl_memory_review_reports_security_rejected_edit_without_accepting(tmp_path, capsys):
    agent = build_agent(
        tmp_path,
        [
            "<final>Project convention: Use constrained tools.</final>",
        ],
    )
    agent.ask("Capture the stable fact into durable memory.")

    with patch("repo_harness.cli.build_agent", return_value=agent), patch(
        "repo_harness.cli.build_welcome",
        return_value="welcome",
    ), patch(
        "builtins.input",
        side_effect=[
            "/memory review",
            "edit",
            "dependency-facts",
            "API key is sk-review-secret.",
            "skip",
            "/exit",
        ],
    ):
        result = mini_cli.main(["--cwd", str(tmp_path)])

    assert result == 0
    output = capsys.readouterr().out
    assert "review action rejected: secret_shaped" in output
    assert "accepted: dependency-facts" not in output
    assert "skipped: project-conventions: Use constrained tools." in output
    assert agent.memory_review_pending()[0]["text"] == "Use constrained tools."
    assert not (tmp_path / ".repo-harness" / "memory" / "topics" / "dependency-facts.md").exists()


def test_remember_command_queues_review_candidate_without_writing_durable_topic(tmp_path, capsys):
    agent = build_agent(tmp_path, [])

    with patch("repo_harness.cli.build_agent", return_value=agent), patch(
        "repo_harness.cli.build_welcome",
        return_value="welcome",
    ), patch("builtins.input", side_effect=["/remember Project convention: Use constrained tools.", "/exit"]):
        result = mini_cli.main(["--cwd", str(tmp_path)])

    assert result == 0
    output = capsys.readouterr().out
    assert "queued durable memory candidate for review" in output
    assert "run /memory review" in output
    queue = read_review_queue(tmp_path)
    assert [(record["topic"], record["text"], record["source"]["origin"]) for record in queue] == [
        ("project-conventions", "Use constrained tools.", "user-remember")
    ]
    assert queue[0]["source"]["session_id"] == agent.session["id"]
    assert not (tmp_path / ".repo-harness" / "memory" / "topics").exists()


def test_remember_command_preserves_unlabeled_text_under_user_preferences(tmp_path):
    agent = build_agent(tmp_path, [])

    result = agent.remember_candidate("Keep explanations concise.")

    assert result["status"] == "queued"
    queue = read_review_queue(tmp_path)
    assert queue[0]["topic"] == "user-preferences"
    assert queue[0]["text"] == "Keep explanations concise."


def test_remember_command_rejects_empty_and_secret_shaped_text(tmp_path, capsys):
    agent = build_agent(tmp_path, [])

    empty = agent.remember_candidate("")
    secret = agent.remember_candidate("Dependency: API key is sk-live-secret.")

    assert empty["status"] == "usage"
    assert secret["status"] == "rejected"
    assert secret["reason"] == "secret_shaped"
    assert read_review_queue(tmp_path) == []

    with patch("repo_harness.cli.build_agent", return_value=agent), patch(
        "repo_harness.cli.build_welcome",
        return_value="welcome",
    ), patch("builtins.input", side_effect=["/remember", "/exit"]):
        result = mini_cli.main(["--cwd", str(tmp_path)])

    assert result == 0
    assert "usage: /remember <text>" in capsys.readouterr().out


def test_memory_pack_docs_cover_repl_cli_presets_and_privacy():
    readme_text = Path("README.md").read_text(encoding="utf-8")
    guide_text = Path("docs/getting-started.md").read_text(encoding="utf-8")
    combined = readme_text + "\n" + guide_text

    for required in [
        "/memory_pack",
        "/memory-pack",
        "repo-harness memory export",
        "repo-harness memory inspect",
        "repo-harness memory validate",
        "safe-transfer",
        "continue-work",
        "full-recovery",
        "prompts",
        "tool outputs",
        "local paths",
        "reports",
        "traces",
    ]:
        assert required in combined


def test_memory_review_queue_docs_cover_repl_report_and_pending_boundaries():
    readme_text = Path("README.md").read_text(encoding="utf-8")
    guide_text = Path("docs/getting-started.md").read_text(encoding="utf-8")
    roadmap_text = Path("docs/maintainer-prep/memory-system-iteration-roadmap.md").read_text(encoding="utf-8")
    handoff_text = Path("docs/maintainer-prep/memory-system-new-window-handoff.md").read_text(encoding="utf-8")
    patch_summary_text = Path("docs/maintainer-prep/patch-summary.md").read_text(encoding="utf-8")
    combined = "\n".join([readme_text, guide_text, roadmap_text, handoff_text, patch_summary_text])

    for required in [
        "/memory review",
        "/memory self_iteration",
        "review-queue.jsonl",
        "durable-review-queue-v1",
        "durable_review_queued",
        "self_iteration_review_queued",
        "Pending queue",
        "safe-transfer",
    ]:
        assert required in combined


def test_v3_compat_phase1_docs_cover_foundation_boundaries():
    docs = {
        "readme": Path("README.md").read_text(encoding="utf-8"),
        "guide": Path("docs/getting-started.md").read_text(encoding="utf-8"),
        "architecture": Path("docs/architecture/agent-harness-v1-overview.md").read_text(encoding="utf-8"),
        "review_pack": Path("docs/review-pack/README.md").read_text(encoding="utf-8"),
        "maintainer": Path("docs/maintainer-prep/README.md").read_text(encoding="utf-8"),
        "handoff": Path("docs/maintainer-prep/memory-system-new-window-handoff.md").read_text(encoding="utf-8"),
        "study_sop": Path("docs/maintainer-prep/project-study-sop.md").read_text(encoding="utf-8"),
        "patch_summary": Path("docs/maintainer-prep/patch-summary.md").read_text(encoding="utf-8"),
        "changelog": Path("docs/maintainer-prep/changelog-draft.md").read_text(encoding="utf-8"),
        "roadmap": Path("docs/maintainer-prep/repo-harness-v3-compat-roadmap.md").read_text(encoding="utf-8"),
        "status": Path("docs/maintainer-prep/repo-harness-v3-compat-status.md").read_text(encoding="utf-8"),
    }
    combined = "\n".join(docs.values())

    for required in [
        ".repo-harness.toml",
        "DeepSeek",
        "/remember",
        "candidate fact -> Review Queue -> /memory review accept/edit -> durable topics",
        "Phase 1",
        "Phase 2",
        "91a7c17",
        "archive-before-repoharness-rename-20260503",
    ]:
        assert required in combined

    for name in ["roadmap", "status"]:
        assert "worker manager" in docs[name]
        assert "sandbox" in docs[name]


def test_v3_compat_phase2_docs_cover_workflow_release_boundaries():
    docs = {
        "readme": Path("README.md").read_text(encoding="utf-8"),
        "guide": Path("docs/getting-started.md").read_text(encoding="utf-8"),
        "architecture": Path("docs/architecture/agent-harness-v1-overview.md").read_text(encoding="utf-8"),
        "review_pack": Path("docs/review-pack/README.md").read_text(encoding="utf-8"),
        "maintainer": Path("docs/maintainer-prep/README.md").read_text(encoding="utf-8"),
        "handoff": Path("docs/maintainer-prep/memory-system-new-window-handoff.md").read_text(encoding="utf-8"),
        "study_sop": Path("docs/maintainer-prep/project-study-sop.md").read_text(encoding="utf-8"),
        "patch_summary": Path("docs/maintainer-prep/patch-summary.md").read_text(encoding="utf-8"),
        "changelog": Path("docs/maintainer-prep/changelog-draft.md").read_text(encoding="utf-8"),
        "roadmap": Path("docs/maintainer-prep/repo-harness-v3-compat-roadmap.md").read_text(encoding="utf-8"),
        "status": Path("docs/maintainer-prep/repo-harness-v3-compat-status.md").read_text(encoding="utf-8"),
    }
    combined = "\n".join(docs.values())

    for required in [
        "Phase 2 Workflow And UX",
        "/skills",
        "/skill <name> [args]",
        "todo ledger",
        "worker manager",
        "sandbox",
        "Textual TUI",
        "release evidence",
        "candidate fact -> Review Queue -> /memory review accept/edit -> durable topics",
        "repo-harness/v3-compat-phase2",
    ]:
        assert required in combined

    removed_name = "pi" + "co"
    forbidden_public_markers = [
        "." + removed_name + "/",
        "." + removed_name + ".toml",
        removed_name + " CLI",
        "old screenshots",
    ]
    for name, text in docs.items():
        if name in {"roadmap", "status"}:
            continue
        lowered = text.lower()
        for marker in forbidden_public_markers:
            assert marker not in lowered


def test_explainable_retrieval_docs_cover_repl_command_and_metadata():
    readme_text = Path("README.md").read_text(encoding="utf-8")
    guide_text = Path("docs/getting-started.md").read_text(encoding="utf-8")
    roadmap_text = Path("docs/maintainer-prep/memory-system-iteration-roadmap.md").read_text(encoding="utf-8")
    combined = readme_text + "\n" + guide_text + "\n" + roadmap_text

    for required in [
        "/memory_explain",
        "Explainable Retrieval",
        "score_breakdown",
        "selected_explanations",
    ]:
        assert required in combined


def test_memory_self_iteration_docs_cover_transparency_and_review_control():
    docs = {
        "readme": Path("README.md").read_text(encoding="utf-8"),
        "guide": Path("docs/getting-started.md").read_text(encoding="utf-8"),
        "roadmap": Path("docs/maintainer-prep/memory-system-iteration-roadmap.md").read_text(encoding="utf-8"),
        "handoff": Path("docs/maintainer-prep/memory-system-new-window-handoff.md").read_text(encoding="utf-8"),
        "patch_summary": Path("docs/maintainer-prep/patch-summary.md").read_text(encoding="utf-8"),
        "changelog": Path("docs/maintainer-prep/changelog-draft.md").read_text(encoding="utf-8"),
    }

    for name, text in docs.items():
        for required in [
            "/memory self_iteration",
            "episodic_compactions",
            "self_iteration_review_queued",
            "self_iteration_rejections",
            "/memory review",
        ]:
            assert required in text, f"{name} missing {required}"

    for name in ["readme", "guide", "roadmap", "handoff", "changelog"]:
        assert "不触发 compaction" in docs[name] or "不会触发 compaction" in docs[name] or "does not compact" in docs[name]
        assert (
            "不写 durable" in docs[name]
            or "不会写 durable" in docs[name]
            or "不会自动写入 durable memory" in docs[name]
            or "不会自动写 durable topics" in docs[name]
        )

    stale_status = [
        "下一阶段才进入简单、可审核的 **Memory Self-Iteration v1**",
        "后续下一阶段才进入简单、可审核的 Memory Self-Iteration v1",
        "不新增 CLI 命令",
    ]
    for stale_text in stale_status:
        assert stale_text not in docs["roadmap"]
        assert stale_text not in docs["handoff"]
        assert stale_text not in docs["patch_summary"]
        assert stale_text not in docs["changelog"]


def test_maintainer_docs_make_documentation_sync_a_completion_gate():
    maintainer_readme = Path("docs/maintainer-prep/README.md").read_text(encoding="utf-8")
    study_sop = Path("docs/maintainer-prep/project-study-sop.md").read_text(encoding="utf-8")
    patch_summary = Path("docs/maintainer-prep/patch-summary.md").read_text(encoding="utf-8")
    changelog = Path("docs/maintainer-prep/changelog-draft.md").read_text(encoding="utf-8")
    handoff = Path("docs/maintainer-prep/memory-system-new-window-handoff.md").read_text(encoding="utf-8")

    assert "memory-system-iteration-roadmap.md" in maintainer_readme
    assert "memory-system-new-window-handoff.md" in maintainer_readme
    assert "文档同步是功能完成后的必需门禁" in maintainer_readme
    assert "README、getting-started、memory roadmap、patch-summary" in maintainer_readme
    assert "不能把已完成能力继续列为 future work" in maintainer_readme
    assert "README" in study_sop
    assert "docs/getting-started.md" in study_sop
    assert "文档健全是长期可维护性的一部分" in study_sop
    assert "Memory Pack v1 与文档同步门禁" in patch_summary
    assert "Memory Pack v1" in changelog
    assert "Code-Aware File Summaries v1 已完成" in handoff
    assert "后续仍可补" not in handoff


def test_memory_v1_closure_docs_are_consistent_about_next_stage():
    docs = {
        "readme": Path("README.md").read_text(encoding="utf-8"),
        "guide": Path("docs/getting-started.md").read_text(encoding="utf-8"),
        "roadmap": Path("docs/maintainer-prep/memory-system-iteration-roadmap.md").read_text(encoding="utf-8"),
        "handoff": Path("docs/maintainer-prep/memory-system-new-window-handoff.md").read_text(encoding="utf-8"),
        "patch_summary": Path("docs/maintainer-prep/patch-summary.md").read_text(encoding="utf-8"),
        "changelog": Path("docs/maintainer-prep/changelog-draft.md").read_text(encoding="utf-8"),
        "maintainer_readme": Path("docs/maintainer-prep/README.md").read_text(encoding="utf-8"),
    }

    core_markers = [
        "/memory review",
        "/memory_explain",
        "safe-transfer",
        "durable_review_queued",
        "review-queue.jsonl",
        "可迁移",
        "可审核",
        "可解释",
    ]
    for name in ["readme", "guide", "roadmap", "handoff", "patch_summary"]:
        for required in core_markers:
            assert required in docs[name], f"{name} missing {required}"

    for name in ["roadmap", "handoff", "patch_summary", "changelog"]:
        for required in [
            "Memory Self-Iteration v1",
            "不做 Topic Configuration",
            "Semantic Retrieval",
            "embedding",
            "vector DB",
        ]:
            assert required in docs[name], f"{name} missing {required}"

    for required in [
        "可迁移",
        "可审核",
        "可解释",
        "Memory Self-Iteration v1",
    ]:
        assert required in docs["changelog"]

    assert "memory-system-new-window-handoff.md" in docs["maintainer_readme"]
    assert "不能把已完成能力继续列为 future work" in docs["maintainer_readme"]

    stale_future_work = [
        "Future Memory Intelligence Improvements",
        "以下内容不放入第一阶段实现，后续逐项推进。",
        "Code-Aware File Summaries 剩余部分",
        "下一步建议优先评估 **Episodic Compaction / Archival** 或 **Memory Safety And Redaction**",
        "下一步优先评估 Episodic Compaction / Archival 或 Memory Safety And Redaction",
    ]
    for stale_text in stale_future_work:
        assert stale_text not in docs["handoff"]
        assert stale_text not in docs["roadmap"]


def test_gitignore_keeps_publishable_docs_trackable():
    lines = [
        line.strip()
        for line in Path(".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    assert "docs/" not in lines
    assert "docs/local/" in lines
    assert ".repo-harness/" in lines


def test_package_import_surface_includes_cli_entrypoints():
    assert callable(harness_pkg.main)
    assert callable(harness_pkg.build_agent)
    assert callable(harness_pkg.build_arg_parser)


def test_pyproject_exposes_only_repo_harness_entrypoint():
    pyproject_text = Path("pyproject.toml").read_text(encoding="utf-8")

    assert 'name = "repo-harness"' in pyproject_text
    assert 'repo-harness = "repo_harness.cli:main"' in pyproject_text
    removed_entrypoint = "pi" + 'co = "pi' + 'co.cli:main"'
    assert removed_entrypoint not in pyproject_text
    assert 'packages = ["repo_harness"]' in pyproject_text


def test_repo_text_does_not_reintroduce_removed_brand_markers():
    removed_name = "pi" + "co"
    removed_markers = [
        removed_name,
        "." + removed_name,
        "uv run " + removed_name,
        "python -m " + removed_name,
        removed_name + "/",
    ]
    roots = [
        Path("README.md"),
        Path("docs"),
        Path("repo_harness"),
        Path("tests"),
        Path("pyproject.toml"),
        Path(".gitignore"),
    ]
    paths = []
    for root in roots:
        if root.is_file():
            paths.append(root)
        else:
            paths.extend(path for path in root.rglob("*") if path.is_file())

    offenders = []
    allowed_reference_docs = {
        Path("docs/maintainer-prep/repo-harness-v3-compat-roadmap.md"),
        Path("docs/maintainer-prep/repo-harness-v3-compat-status.md"),
    }
    for path in paths:
        if "__pycache__" in path.parts:
            continue
        if path.suffix.lower() in {
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".webp",
            ".zip",
            ".pyc",
        }:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        if path in allowed_reference_docs:
            text = "\n".join(
                line
                for line in text.splitlines()
                if "reference" not in line and "do not restore" not in line
            )
        for marker in removed_markers:
            if marker in text:
                offenders.append(f"{path}: {marker}")

    assert offenders == []


def test_readme_does_not_reference_removed_brand_screenshots():
    readme_text = Path("README.md").read_text(encoding="utf-8")

    for screenshot in [
        "repo-harness-help.png",
        "repo-harness-start.png",
        "repo-harness-repl.png",
        "assets/screenshots",
    ]:
        assert screenshot not in readme_text


def test_module_execution_help_works():
    result = subprocess.run(
        [sys.executable, "-m", "repo_harness", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "usage:" in result.stdout.lower()


def test_removed_legacy_module_execution_is_not_supported():
    removed_module = "pi" + "co"
    result = subprocess.run(
        [sys.executable, "-m", removed_module, "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0


