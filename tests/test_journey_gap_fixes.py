"""e2e 补充查验发现的两处用户旅程断点的回归测试。

1. /memory review 的 EOF/空输入死循环：prompt_choice 把 EOFError 与
   KeyboardInterrupt 吞成空串，review 的 while True 对空输入没有终止
   语义——管道环境 stdin 耗尽后 100% CPU 刷屏，用户按 Ctrl-C 也退不出
   review。空输入必须视为离开 review。

2. auto-compact 的 rendered-token 比率分支在真实预算计算下算术不可达：
   section 预算先把 history 裁到预算内，token 估算用的是裁剪后文本，
   0.375×window < 0.84×window 恒成立（任何窗口、默认 max_new_tokens）。
   Stage 6 单测通过直接注入 usage/total_budget 绕过了真实预算计算。
   真实压力信号是 history 的 raw 需求超过其 section 预算——那才是
   "预算削减静默丢历史"实际发生的位置。
"""


from repo_harness import FakeModelClient, RepoHarness, SessionStore, WorkspaceContext
from repo_harness.cli import run_memory_review


class _ExplodingDisplay:
    """prompt_choice 超过 limit 次即判定死循环。"""

    def __init__(self, answers, limit=25):
        self.answers = list(answers)
        self.calls = 0
        self.limit = limit
        self.infos = []

    def prompt_choice(self, prompt, choices=None):
        self.calls += 1
        if self.calls > self.limit:
            raise AssertionError(
                f"infinite loop: prompt_choice called {self.calls} times"
            )
        if self.answers:
            return self.answers.pop(0)
        return ""  # stdin 耗尽后 prompt_choice 的实际返回

    def prompt_text(self, prompt, default=""):
        return ""

    def show_info(self, message):
        self.infos.append(str(message))

    def show_warning(self, message):
        pass

    def show_success(self, message):
        pass


def _agent(tmp_path):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    return RepoHarness(
        model_client=FakeModelClient(["<final>ok</final>"]),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".repo-harness" / "sessions"),
    )


def _queue_candidate(agent):
    result = agent.remember_candidate("the workspace uses pipeline alpha")
    assert result.get("status") in {"queued", "ok", "duplicate"}, result


def test_memory_review_blank_input_leaves_review(tmp_path):
    """EOF/空输入（含被吞掉的 Ctrl-C）必须离开 review，而不是刷屏死循环。"""
    agent = _agent(tmp_path)
    _queue_candidate(agent)

    display = _ExplodingDisplay([])
    run_memory_review(agent, display=display)  # 不得死循环、不得抛异常

    assert display.calls >= 1, "review 应该至少读过一次输入"


def test_memory_review_ctrl_c_as_blank_leaves_review(tmp_path):
    """KeyboardInterrupt 被 prompt_choice 吞成空串后同样必须离开 review。"""
    agent = _agent(tmp_path)
    _queue_candidate(agent)

    display = _ExplodingDisplay([])
    run_memory_review(agent, display=display)
    # 没有 AssertionError 即通过；候选保留在队列中未丢失。
    assert len(list(agent.memory_review_pending())) == 1


def test_memory_review_accept_still_works(tmp_path):
    """修复不得破坏正常 accept 流程。"""
    agent = _agent(tmp_path)
    _queue_candidate(agent)

    display = _ExplodingDisplay(["accept"])
    run_memory_review(agent, display=display)

    topics = tmp_path / ".repo-harness" / "memory" / "topics"
    promoted = topics.is_dir() and any(topics.glob("*.md"))
    assert promoted, "accept 后候选应提升为 durable topic 文件"


def test_prompt_session_disabled_for_non_tty_stdin(monkeypatch, tmp_path):
    """非 tty stdin 必须禁用 prompt_toolkit（REPL 单一输入读取器）。

    pt 在管道 stdin 上会预读缓冲，与 review/审批的裸 input() 撕开输入
    流：输入行被 pt 吞掉再当作 REPL 消息吐出。非 tty 一律 input()。
    """
    import io

    from repo_harness.cli import _build_prompt_session

    monkeypatch.setattr("sys.stdin", io.StringIO(""))

    assert _build_prompt_session(tmp_path) is None


def test_auto_compact_triggers_on_history_budget_pressure(tmp_path):
    """history raw 需求超过其 section 预算时必须触发 auto-compact。

    fake 模型 window=4096 → 预算 floor 12000 字符、history 预算 6000。
    预填 14 条长历史（raw ~29k 字符 > 6000）：rendered 比率路径永远到
    不了阈值，真实信号是 raw 超预算。
    """
    agent = _agent(tmp_path)
    for _ in range(7):
        agent.session["history"].append({"role": "user", "content": "task filler " * 200})
        agent.session["history"].append({"role": "assistant", "content": "result filler " * 200})

    events = list(agent.engine.run_turn("finish now"))

    events_text = agent.session_event_bus.path.read_text(encoding="utf-8")
    assert "auto_compaction" in events_text, (
        "history raw 需求超过 section 预算时应触发 auto_compaction；"
        f"events: {events_text[-400:]}"
    )
    assert any(event.get("type") == "final" for event in events)
