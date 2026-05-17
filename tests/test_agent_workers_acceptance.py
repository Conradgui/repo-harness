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
