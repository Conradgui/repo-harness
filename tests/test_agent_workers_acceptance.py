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
