"""会话持久化与收尾链的崩溃安全（finding: session-persistence-not-crash-safe）。

此前 save() 非原子写（write_text 直接覆盖）、final 收尾链没有异常保护、
CLI 中断时收尾完全跳过——任一故障都会让 run 永久悬在 running 状态，
或在磁盘上留下半截 JSON。
"""

import json
import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import repo_harness.session_store as session_store_module
from repo_harness import FakeModelClient, RepoHarness, SessionStore, WorkspaceContext
from repo_harness.cli import _persist_interrupted_state
from repo_harness.session_store import SessionLoadError
from repo_harness.task_state import STATUS_RUNNING, TaskState


def _agent(tmp_path, outputs):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    return RepoHarness(
        model_client=FakeModelClient(outputs),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".repo-harness" / "sessions"),
    )


# --- SessionStore.save：原子写与并发串行化 ---


def test_save_failure_keeps_previous_file_intact(tmp_path):
    """写入中途失败（replace 前崩溃）：旧文件完好，不出现半截 JSON。"""
    store = SessionStore(tmp_path / "sessions")
    store.save({"id": "s1", "history": [{"n": 1}]})

    with patch("os.replace", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            store.save({"id": "s1", "history": [{"n": 1}, {"n": 2}]})

    reloaded = store.load("s1")
    assert reloaded["history"] == [{"n": 1}]


def test_concurrent_saves_always_leave_parseable_file(tmp_path):
    """worker 线程与主线程并发保存：文件始终是完整的 JSON。"""
    store = SessionStore(tmp_path / "sessions")
    session = {"id": "s1", "history": []}
    errors = []

    def writer(count):
        try:
            for i in range(count):
                session["history"].append({"i": i, "pad": "x" * (i % 7) * 100})
                store.save(session)
        except Exception as exc:  # pragma: no cover - 失败即测试失败
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(100,)) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert errors == []
    reloaded = store.load("s1")
    assert reloaded["id"] == "s1"
    assert len(reloaded["history"]) == 300


def test_save_retries_through_concurrent_mutation(tmp_path):
    """dumps 撞上并发修改（dict changed size）时重试，而不是丢掉保存。"""
    store = SessionStore(tmp_path / "sessions")
    session = {"id": "s1", "history": []}
    original_dumps = json.dumps
    calls = {"count": 0}

    def flaky_dumps(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("dictionary changed size during iteration")
        return original_dumps(*args, **kwargs)

    with patch.object(
        session_store_module,
        "json",
        SimpleNamespace(dumps=flaky_dumps, loads=json.loads),
    ):
        store.save(session)

    assert calls["count"] >= 2
    assert store.load("s1")["id"] == "s1"


def test_load_corrupted_session_raises_clear_error(tmp_path):
    """损坏的 session 文件给出明确错误，而不是裸 JSONDecodeError。"""
    store = SessionStore(tmp_path / "sessions")
    (tmp_path / "sessions").mkdir(parents=True, exist_ok=True)
    (tmp_path / "sessions" / "s1.json").write_text('{"id": "s1", "his', encoding="utf-8")

    with pytest.raises(SessionLoadError) as excinfo:
        store.load("s1")

    assert "corrupt" in str(excinfo.value).lower()


# --- engine final 收尾链：任一环节异常仍写入失败终态 ---


@pytest.mark.parametrize(
    "target,attribute",
    [
        ("runtime", "promote_durable_memory"),
        ("runtime", "create_checkpoint"),
        ("runtime", "_finalize_runtime_evidence"),
        ("run_store", "write_task_state"),
        ("run_store", "write_report"),
    ],
)
def test_final_chain_exception_persists_failed_terminal_state(tmp_path, target, attribute):
    """final 收尾链异常：task_state 与 report 必须以失败终态落盘。"""
    agent = _agent(tmp_path, ["<final>done</final>"])
    owner = agent if target == "runtime" else agent.run_store
    boom = RuntimeError("finalization exploded")
    original = getattr(owner, attribute)

    if attribute == "write_task_state":
        # write_task_state 在循环开头（status=running）也会被调；
        # 只有终态化之后的第一次调用才注入故障。
        fired = {"done": False}

        def flaky(task_state, *args, **kwargs):
            if task_state.status != STATUS_RUNNING and not fired["done"]:
                fired["done"] = True
                raise boom
            return original(task_state, *args, **kwargs)

        patcher = patch.object(owner, attribute, flaky)
    elif attribute == "write_report":
        calls = {"count": 0}

        def flaky(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise boom
            return original(*args, **kwargs)

        patcher = patch.object(owner, attribute, flaky)
    else:
        patcher = patch.object(owner, attribute, side_effect=boom)

    with patcher:
        events = list(agent.engine.run_turn("do work"))

    assert not any(event["type"] == "final" for event in events)
    finished = [event for event in events if event["type"] == "turn_finished"]
    assert finished and finished[-1]["status"] == "failed"

    saved_state = json.loads(
        (agent.current_run_dir / "task_state.json").read_text(encoding="utf-8")
    )
    assert saved_state["status"] == "failed"
    assert saved_state["stop_reason"] == "persistence_error"

    report = json.loads((agent.current_run_dir / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed"


def test_final_chain_without_exception_stays_completed(tmp_path):
    """对照：收尾链健康时行为不变——completed 终态 + report 正常。"""
    agent = _agent(tmp_path, ["<final>all good</final>"])

    events = list(agent.engine.run_turn("do work"))

    assert events[-1]["type"] == "turn_finished"
    assert events[-1]["status"] == "completed"
    saved_state = json.loads(
        (agent.current_run_dir / "task_state.json").read_text(encoding="utf-8")
    )
    assert saved_state["status"] == "completed"


# --- CLI 中断：session 落盘 + running run 标记 interrupted ---


def test_persist_interrupted_state_marks_running_run_and_saves_session(tmp_path):
    agent = _agent(tmp_path, [])
    task_state = TaskState.create(task_id="task_1", user_request="work")
    agent.current_task_state = task_state
    agent.current_run_dir = agent.run_store.start_run(task_state)
    agent.run_store.write_task_state(task_state)

    _persist_interrupted_state(agent)

    saved_state = json.loads(
        (agent.current_run_dir / "task_state.json").read_text(encoding="utf-8")
    )
    assert saved_state["status"] == "stopped"
    assert saved_state["stop_reason"] == "interrupted"
    session = json.loads(agent.session_path.read_text(encoding="utf-8"))
    assert session["id"] == agent.session["id"]


def test_persist_interrupted_state_tolerates_broken_agent(tmp_path):
    """中断兜底自身不允许再抛：agent 处于残缺状态时静默尽力而为。"""
    agent = _agent(tmp_path, [])

    with patch.object(
        agent, "session_store", SimpleNamespace(save=RuntimeError("store gone"))
    ):
        _persist_interrupted_state(agent)  # 不抛即通过

    with patch.object(agent, "current_task_state", None):
        _persist_interrupted_state(agent)  # 不抛即通过
