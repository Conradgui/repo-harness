"""Act 完成验证门：改动后没有验证证据的 final 不得进入 success 终态。

对照物是同一循环里 plan 模式的 can_finish() 硬门；act 模式此前允许模型
一句话宣告成功即触发 success 终态与成功报告（finding:
act-final-without-verification-gate）。
"""

import json

from conftest import build_agent

WRITE_RESULT = (
    '<tool name="write_file" path="notes/result.txt"><content>ok\n</content></tool>'
)
RUN_PYTEST_VERSION = (
    '<tool>{"name":"run_shell","args":'
    '{"command":"python -m pytest --version","timeout":60}}</tool>'
)
FINAL = "<final>Wrote it.</final>"


def run(agent, message="create the result file"):
    return list(agent.engine.run_turn(message))


def read_report(agent):
    return json.loads((agent.current_run_dir / "report.json").read_text(encoding="utf-8"))


def test_final_after_changes_without_verification_is_not_success(tmp_path):
    """改了文件、没跑任何验证就宣告完成 → 门拦截，run 不进 success 终态。"""
    agent = build_agent(tmp_path, [WRITE_RESULT, FINAL, FINAL])

    events = run(agent)

    notices = [event for event in events if event["type"] == "runtime_notice"]
    assert len(notices) == 2, "gate must keep intercepting repeated unverified finals"
    assert "verification" in notices[0]["content"].lower()
    assert agent.current_task_state.status != "completed"
    assert read_report(agent)["status"] != "completed"


def test_gate_notice_guides_model_to_verify_then_finish(tmp_path):
    """被拦后模型跑验证再宣告完成 → 放行进入 success 终态。"""
    agent = build_agent(
        tmp_path,
        [WRITE_RESULT, FINAL, RUN_PYTEST_VERSION, "<final>Verified.</final>"],
    )

    events = run(agent)

    assert any(event["type"] == "runtime_notice" for event in events)
    assert agent.current_task_state.status == "completed"
    assert agent.current_task_state.final_answer == "Verified."


def test_verification_before_changes_does_not_satisfy_gate(tmp_path):
    """验证证据必须覆盖最后一次改动：先验证后改动不算数。"""
    agent = build_agent(tmp_path, [RUN_PYTEST_VERSION, WRITE_RESULT, FINAL, FINAL])

    events = run(agent)

    assert any(event["type"] == "runtime_notice" for event in events)
    assert agent.current_task_state.status != "completed"


def test_final_without_changes_is_not_gated(tmp_path):
    """纯问答没有改动，final 直通，行为不变。"""
    agent = build_agent(tmp_path, ["<final>Just answering.</final>"])

    events = run(agent, "just answer")

    assert not any(event["type"] == "runtime_notice" for event in events)
    assert agent.current_task_state.status == "completed"


def test_bare_text_final_after_changes_is_not_success(tmp_path):
    """parse() 把裸文本兜底成 final 的路径同样过门，不得误判为成功完成。"""
    agent = build_agent(
        tmp_path,
        [WRITE_RESULT, "I am done with the change.", "still done."],
    )

    events = run(agent)

    assert any(event["type"] == "runtime_notice" for event in events)
    assert agent.current_task_state.status != "completed"


def test_verification_gate_can_be_disabled_by_feature_flag(tmp_path):
    """ADR-002：边界用开关表达，关掉门走配置而不是改代码。"""
    agent = build_agent(
        tmp_path,
        [WRITE_RESULT, FINAL],
        feature_flags={"verification_gate": False},
    )

    events = run(agent)

    assert not any(event["type"] == "runtime_notice" for event in events)
    assert agent.current_task_state.status == "completed"


def test_echoing_verification_keyword_does_not_satisfy_gate(tmp_path):
    """哑命令提到 runner 名不算验证：门拦的是没有真实验证，不是没提过验证。"""
    agent = build_agent(
        tmp_path,
        [
            WRITE_RESULT,
            '<tool>{"name":"run_shell","args":{"command":"echo pytest passed","timeout":20}}</tool>',
            FINAL,
            FINAL,
        ],
    )

    events = run(agent)

    assert any(event["type"] == "runtime_notice" for event in events)
    assert agent.current_task_state.status != "completed"


def test_is_verification_command_matches_common_runners():
    from repo_harness.runtime_evidence import is_verification_command

    assert is_verification_command("uv run python -m pytest -q")
    assert is_verification_command("python -m pytest tests/ -q")
    assert is_verification_command("pytest")
    assert is_verification_command("npm test")
    assert is_verification_command("npm run build")
    assert is_verification_command("ruff check .")
    assert is_verification_command("make test")
    assert not is_verification_command("ls -la")
    assert not is_verification_command("echo pytest passed")
    assert not is_verification_command("cat notes/result.txt")
    assert not is_verification_command("")
