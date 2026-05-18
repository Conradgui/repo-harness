from repo_harness import FakeModelClient, RepoHarness, SessionStore, WorkspaceContext


def build_agent(tmp_path, outputs):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    return RepoHarness(
        model_client=FakeModelClient(outputs),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".repo-harness" / "sessions"),
        approval_policy="auto",
    )


def test_explore_worker_is_read_only_and_records_artifact(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            '<tool>{"name":"write_file","args":{"path":"blocked.txt","content":"nope"}} </tool>',
            "<final>explore done</final>",
        ],
    )

    result = agent.spawn_worker("Inspect", "try to write", subagent_type="Explore")

    assert "explore done" in result["result"]
    assert not (tmp_path / "blocked.txt").exists()
    assert agent.worker_manager.to_dict()["items"][0]["status"] == "completed"
    assert agent.worker_manager.drain_notifications()


def test_worker_write_scope_allows_only_scoped_paths(tmp_path):
    (tmp_path / "allowed.txt").write_text("old\n", encoding="utf-8")
    (tmp_path / "blocked.txt").write_text("old\n", encoding="utf-8")
    agent = build_agent(
        tmp_path,
        [
            '<tool>{"name":"read_file","args":{"path":"blocked.txt","start":1,"end":5}}</tool>',
            '<tool>{"name":"write_file","args":{"path":"blocked.txt","content":"bad\\n"}}</tool>',
            '<tool>{"name":"read_file","args":{"path":"allowed.txt","start":1,"end":5}}</tool>',
            '<tool>{"name":"write_file","args":{"path":"allowed.txt","content":"ok\\n"}}</tool>',
            "<final>worker done</final>",
        ],
    )

    result = agent.spawn_worker("Patch scoped", "update files", subagent_type="worker", write_scope=["allowed.txt"])

    assert "worker done" in result["result"]
    assert (tmp_path / "blocked.txt").read_text(encoding="utf-8") == "old\n"
    assert (tmp_path / "allowed.txt").read_text(encoding="utf-8") == "ok\n"


def test_worker_can_continue_and_stop_with_notifications(tmp_path):
    (tmp_path / "notes").mkdir()
    agent = build_agent(
        tmp_path,
        [
            '<tool>{"name":"write_file","args":{"path":"notes/first.txt","content":"one\\n"}}</tool>',
            "<final>first done</final>",
            '<tool>{"name":"write_file","args":{"path":"notes/second.txt","content":"two\\n"}}</tool>',
            "<final>second done</final>",
        ],
    )

    first = agent.spawn_worker("Write first", "write first", subagent_type="worker", write_scope=["notes"])
    second = agent.worker_manager.send(first["id"], "write second")
    stopped = agent.worker_manager.stop(first["id"])

    assert first["status"] == "running"
    assert second["status"] == "completed"
    assert stopped["status"] == "stopped"
    assert (tmp_path / "notes" / "first.txt").exists()
    assert (tmp_path / "notes" / "second.txt").exists()
    assert agent.worker_manager.drain_notifications()


def test_plan_mode_allows_only_explore_workers(tmp_path):
    agent = build_agent(tmp_path, ["<final>explore done</final>"])
    agent.enter_plan_mode("workers")

    explore = agent.spawn_worker("Inspect", "inspect", subagent_type="Explore")

    assert explore["subagent_type"] == "Explore"
    try:
        agent.spawn_worker("Patch", "patch", subagent_type="worker", write_scope=["README.md"])
    except ValueError as exc:
        assert "plan mode only allows Explore" in str(exc)
    else:
        raise AssertionError("write worker should be rejected in plan mode")


def test_background_worker_uses_model_client_factory_and_reports_artifacts(tmp_path):
    calls = []

    def factory(**kwargs):
        calls.append(kwargs)
        return FakeModelClient(["<final>background done</final>"])

    agent = RepoHarness(
        model_client=FakeModelClient([]),
        model_client_factory=factory,
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".repo-harness" / "sessions"),
        approval_policy="auto",
    )

    started = agent.worker_manager.spawn("background", "work in background", subagent_type="worker", write_scope=["out"])
    task = agent.worker_manager._tasks[started["id"]]
    task.thread.join(10)
    item = agent.worker_manager.to_dict()["items"][0]

    assert started["status"] == "started"
    assert calls and calls[0]["subagent_type"] == "worker"
    assert item["status"] == "completed"
    assert item["result"] == "background done"
    assert item["report_path"]
    assert item["trace_path"]
    assert agent.worker_manager.drain_notifications() == ["agent_1 completed: background done"]


def test_running_background_worker_rejects_continue_until_finished(tmp_path):
    class BlockingClient(FakeModelClient):
        def complete(self, prompt, max_new_tokens, **kwargs):
            import time

            time.sleep(0.2)
            return "<final>blocked done</final>"

    agent = RepoHarness(
        model_client=FakeModelClient([]),
        model_client_factory=lambda **kwargs: BlockingClient([]),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".repo-harness" / "sessions"),
        approval_policy="auto",
    )
    started = agent.worker_manager.spawn("background", "slow", subagent_type="worker", write_scope=["out"])

    try:
        try:
            agent.worker_manager.continue_task(started["id"], "again")
        except ValueError as exc:
            assert "worker is running" in str(exc)
        else:
            raise AssertionError("continue_task should reject running worker")
    finally:
        agent.worker_manager._tasks[started["id"]].thread.join(10)
