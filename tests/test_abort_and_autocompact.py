"""中止协议与自动压缩接线（findings: abort-protocol-unreachable / auto-compact-unwired）。

此前 abort_requested 初始化后没有任何置位代码：REPL 没有停止命令、
worker stop 的 abort_current_turn getattr 恒 None、Ctrl-C 直接抛弃 turn，
engine 里写好的 aborted 收尾路径不可达。AUTO_COMPACT_THRESHOLD 只作为
元数据返回，engine 循环从不检查，唯一兜底是 context_manager 的静默削减。
"""

import json
from unittest.mock import patch

from repo_harness import FakeModelClient, RepoHarness, SessionStore, WorkspaceContext
from repo_harness.cli import HELP_DETAILS, _abort_and_drain, handle_repl_command
from repo_harness.core.engine_helpers import auto_compact_due

TOOL_CALL = '<tool>{"name":"read_file","args":{"path":"README.md"}}</tool>'


def _agent(tmp_path, outputs, **kwargs):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    return RepoHarness(
        model_client=FakeModelClient(outputs),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".repo-harness" / "sessions"),
        **kwargs,
    )


def _saved_state(agent):
    return json.loads((agent.current_run_dir / "task_state.json").read_text(encoding="utf-8"))


def _fill_history(agent, count=60, size=1000):
    for i in range(count):
        agent.session["history"].append(
            {"role": "user", "content": f"msg {i} " + "x" * size}
        )


# --- F6: abort 协议从请求到受控终态 ---


def test_abort_current_turn_sets_flag_and_resets_next_turn(tmp_path):
    """abort_current_turn 置位；新 turn 开始时清除残留标志，不卡死后续轮次。"""
    agent = _agent(tmp_path, ["<final>done</final>"])
    result = agent.abort_current_turn()
    assert agent.abort_requested is True
    assert result["abort_requested"] is True

    events = list(agent.engine.run_turn("hello"))
    assert agent.abort_requested is False
    assert events[-1]["type"] == "turn_finished"
    assert events[-1]["status"] == "completed"


def test_run_tool_skipped_when_abort_requested(tmp_path):
    """abort 置位后，已排队的工具调用被安全跳过而不是执行。"""
    agent = _agent(tmp_path, [])
    agent.abort_requested = True

    result = agent.run_tool("read_file", {"path": "README.md"})

    assert "abort" in result.lower()
    assert "demo" not in result
    assert agent._last_tool_result_metadata["tool_status"] == "rejected"
    assert agent._last_tool_result_metadata["tool_error_code"] == "aborted"


def test_engine_stops_with_aborted_terminal_state(tmp_path):
    """模型返回后收到 abort：run 走 aborted 受控终态并落盘。"""
    agent = _agent(tmp_path, [TOOL_CALL])
    original_complete = agent.model_client.complete

    def complete_then_abort(prompt, max_new_tokens, **kwargs):
        output = original_complete(prompt, max_new_tokens, **kwargs)
        agent.abort_requested = True
        return output

    with patch.object(agent.model_client, "complete", complete_then_abort):
        events = list(agent.engine.run_turn("do work"))

    assert not any(event["type"] == "final" for event in events)
    assert events[-1]["type"] == "turn_finished"
    assert events[-1]["status"] == "stopped"
    assert events[-1]["stop_reason"] == "aborted"
    state = _saved_state(agent)
    assert state["status"] == "stopped"
    assert state["stop_reason"] == "aborted"


def test_repl_stop_command_requests_abort(tmp_path):
    agent = _agent(tmp_path, [])
    handled, should_exit, output = handle_repl_command(agent, "/stop")

    assert handled is True
    assert should_exit is False
    assert agent.abort_requested is True
    assert "abort" in output.lower()
    assert "/stop" in HELP_DETAILS


def test_worker_stop_task_aborts_child_runtime(tmp_path):
    """worker stop 的 abort_current_turn getattr 现在能找到真实方法。"""
    agent = _agent(tmp_path, [])
    manager = agent.worker_manager
    task = manager._new_task("demo", "worker", ["src"])
    manager._tasks[task.id] = task  # 注册（spawn 的职责），不启动线程

    assert callable(getattr(task.runtime, "abort_current_turn", None))
    manager.stop_task(task.id)
    assert task.runtime.abort_requested is True


def test_abort_and_drain_finishes_aborted_terminal_state(tmp_path):
    """Ctrl-C 后的受控中止：置 abort 并消费剩余事件，engine 自己收尾。"""
    agent = _agent(tmp_path, ["<final>unused</final>"])
    events = agent.engine.run_turn("do work")
    assert next(events)["type"] == "turn_started"

    assert _abort_and_drain(agent, events) is True

    state = _saved_state(agent)
    assert state["status"] == "stopped"
    assert state["stop_reason"] == "aborted"


def test_abort_and_drain_tolerates_dead_generator(tmp_path):
    """生成器已耗尽/已死时返回 False，让 CLI 退回中断持久化兜底。"""
    agent = _agent(tmp_path, [])

    assert _abort_and_drain(agent, iter([])) is False

    def broken():
        raise RuntimeError("generator dead")
        yield

    assert _abort_and_drain(agent, broken()) is False


# --- F7: auto-compact 接线与削减声明 ---


def test_auto_compact_due_judgement(tmp_path):
    """触发判定：token 占用超阈值、或本轮已发生预算削减；历史太短不触发。"""
    agent = _agent(tmp_path, [])
    _fill_history(agent, count=20, size=100)

    over = {"total_estimated_tokens": 4000, "context_window": 4096}
    under = {"total_estimated_tokens": 1000, "context_window": 4096}
    assert auto_compact_due(agent, over) is True
    assert auto_compact_due(agent, under) is False
    assert auto_compact_due(agent, {"total_estimated_tokens": 4000}) is False

    assert auto_compact_due(agent, under, {"budget_reductions": [{"section": "history"}]}) is True

    agent.session["history"] = agent.session["history"][:3]
    assert auto_compact_due(agent, over) is False
    assert auto_compact_due(agent, over, {"budget_reductions": [{"section": "history"}]}) is False


def test_auto_compact_triggers_on_token_threshold(tmp_path):
    """输入 token 占用越过 AUTO_COMPACT_THRESHOLD 时自动压缩并继续。"""
    agent = _agent(tmp_path, ["<final>done</final>"])
    agent.context_window = 2000
    _fill_history(agent, count=60, size=1000)

    events = list(agent.engine.run_turn("finish now"))

    compactions = agent.session.get("compactions", [])
    assert compactions and compactions[-1]["trigger"] == "auto"
    assert events[-1]["type"] == "turn_finished"
    assert events[-1]["status"] == "completed"
    # 压缩后的 prompt 不再携带早期长消息（摘要只保留最近 12 条 older）。
    assert "msg 3 " not in agent.model_client.prompts[0]
    assert "msg 30 " not in agent.model_client.prompts[0]


def test_auto_compact_triggers_on_budget_pressure(tmp_path):
    """预算削减即将发生时先压缩历史，而不是直接静默截断。"""
    agent = _agent(tmp_path, ["<final>done</final>"])
    agent.context_manager.total_budget = 3000
    _fill_history(agent, count=30, size=400)

    events = list(agent.engine.run_turn("finish now"))

    compactions = agent.session.get("compactions", [])
    assert compactions and compactions[-1]["trigger"] == "auto"
    assert events[-1]["type"] == "turn_finished"
    assert events[-1]["status"] == "completed"


def test_reduction_notice_visible_to_model(tmp_path):
    """预算削减发生时，prompt 内注入模型可见的显式声明。"""
    agent = _agent(tmp_path, [])
    agent.context_manager.total_budget = 3000
    _fill_history(agent, count=30, size=400)

    prompt, metadata = agent._build_prompt_and_metadata("hello")

    assert metadata["budget_reductions"]
    notice = metadata["context_reduction_notice"]
    assert notice and "reduced" in notice
    assert notice in prompt


def test_manual_compact_remains_manual(tmp_path):
    agent = _agent(tmp_path, [])
    handled, _, _ = handle_repl_command(agent, "/compact")

    assert handled is True
    assert agent.session["compactions"][-1]["trigger"] == "manual"
