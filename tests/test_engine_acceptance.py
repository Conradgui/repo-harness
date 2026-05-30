import json

from repo_harness.providers import ProviderError
from conftest import build_agent


def read_jsonl(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_engine_streams_a_real_session_with_tool_artifacts(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            '<tool name="write_file" path="notes/result.txt"><content>ok\n</content></tool>',
            "<final>Wrote it.</final>",
        ],
    )

    events = list(agent.engine.run_turn("create the result file"))

    assert [event["type"] for event in events] == [
        "turn_started",
        "model_requested",
        "model_parsed",
        "tool_call",
        "tool_result",
        "model_requested",
        "model_parsed",
        "final",
        "turn_finished",
    ]
    assert events[-2]["content"] == "Wrote it."
    assert (tmp_path / "notes" / "result.txt").read_text(encoding="utf-8") == "ok\n"

    persisted_events = read_jsonl(agent.session_event_bus.path)
    assert [event["event"] for event in persisted_events][-6:] == [
        "tool_finished",
        "context_usage_recorded",
        "model_requested",
        "model_parsed",
        "assistant_message",
        "turn_finished",
    ]

    report = json.loads((agent.current_run_dir / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "completed"
    assert report["final_answer"] == "Wrote it."


def test_engine_records_provider_error_as_failed_run(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            ProviderError(
                "rate limited",
                provider="openai",
                model="gpt-test",
                base_url="https://example.test/v1",
                code="rate_limited",
                http_status=429,
                retryable=True,
                attempts=3,
                retry_count=2,
            )
        ],
    )

    events = list(agent.engine.run_turn("call a rate limited provider"))

    assert events[-2]["type"] == "stop"
    assert "rate_limited" in events[-2]["content"]
    assert events[-2]["content"].startswith("模型错误")
    report = json.loads((agent.current_run_dir / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["stop_reason"] == "model_error"
    assert report["prompt_metadata"]["provider_error"]["code"] == "rate_limited"
    assert report["prompt_metadata"]["provider_error"]["retry_count"] == 2

    trace_events = read_jsonl(agent.current_run_dir / "trace.jsonl")
    model_error = next(event for event in trace_events if event["event"] == "model_error")
    assert model_error["error"]["http_status"] == 429

    persisted_events = read_jsonl(agent.session_event_bus.path)
    assert any(
        event["event"] == "model_error" and event["code"] == "rate_limited"
        for event in persisted_events
    )


def test_engine_executes_multiple_tool_calls_from_one_model_response(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            "\n".join(
                [
                    '<tool>{"name":"read_file","args":{"path":"README.md","start":1,"end":1}}</tool>',
                    '<tool>{"name":"list_files","args":{"path":"."}}</tool>',
                ]
            ),
            "<final>Both tools ran.</final>",
        ],
    )

    events = list(agent.engine.run_turn("inspect the workspace"))

    assert [event["type"] for event in events if event["type"] == "tool_call"] == [
        "tool_call",
        "tool_call",
    ]
    tool_history = [item for item in agent.session["history"] if item["role"] == "tool"]
    assert [item["name"] for item in tool_history] == ["read_file", "list_files"]
    assert events[-2]["content"] == "Both tools ran."


def test_empty_response_provider_error_is_retried_once_before_failing(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            ProviderError(
                "empty provider response",
                provider="anthropic",
                model="deepseek-v4-pro",
                base_url="https://api.deepseek.com/anthropic/v1",
                code="empty_response",
                retryable=False,
            ),
            "<final>Recovered.</final>",
        ],
    )

    events = list(agent.engine.run_turn("recover from provider empty response"))

    assert events[-2]["content"] == "Recovered."
    persisted_events = read_jsonl(agent.session_event_bus.path)
    assert any(
        event["event"] == "model_retry_scheduled" and event["code"] == "empty_response"
        for event in persisted_events
    )
