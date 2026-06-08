from pathlib import Path

from tests.benchmark.evaluator import evaluate_tool_runner
from tests.benchmark import run_benchmark


class NoAskAgent:
    max_steps = 5
    session_path = None
    current_run_dir = None
    session = {
        "history": [
            {"role": "tool", "name": "read_file", "content": "ok"},
            {"role": "assistant", "content": "fallback final"},
        ]
    }

    def ask(self, prompt):
        raise AssertionError("evaluator must not call the model")


def test_benchmark_evaluator_uses_existing_response_without_second_model_call(tmp_path):
    task = {
        "id": "BM_TEST",
        "expected_in_response": ["Paragraph"],
        "check_file": "",
    }

    scores = evaluate_tool_runner(
        task,
        NoAskAgent(),
        Path(tmp_path),
        response_text="Paragraph response from first tool run",
    )

    assert scores["response_preview"] == "Paragraph response from first tool run"
    assert scores["tool_calls_count"] == 1


def test_benchmark_runner_imports_without_usability_package():
    assert run_benchmark._provider_model("deepseek") == "deepseek-v4-pro"
    assert run_benchmark._provider_model("mimo") == "mimo-v2.5-pro"
