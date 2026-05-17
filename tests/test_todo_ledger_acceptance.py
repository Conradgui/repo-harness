from repo_harness import FakeModelClient, RepoHarness, SessionStore, WorkspaceContext


def build_agent(tmp_path, outputs=None):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    return RepoHarness(
        model_client=FakeModelClient(outputs or []),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".repo-harness" / "sessions"),
        approval_policy="auto",
    )


def test_todo_tools_persist_in_session_and_prompt(tmp_path):
    agent = build_agent(tmp_path, ["<final>Done.</final>"])

    added = agent.run_tool("todo_add", {"text": "Implement sandbox", "status": "pending"})
    todo_id = agent.todo_ledger.to_dict()["items"][0]["id"]
    updated = agent.run_tool("todo_update", {"id": todo_id, "status": "in_progress"})
    listed = agent.run_tool("todo_list", {})
    answer = agent.ask("Check todos")

    assert "added todo_1" in added
    assert "updated todo_1" in updated
    assert "todo_1 [in_progress] Implement sandbox" in listed
    assert answer == "Done."
    assert agent.session["todos"]["items"][0]["status"] == "in_progress"
    assert "Implement sandbox" in agent.model_client.prompts[-1]
    report = agent.build_report(agent.current_task_state)
    assert report["todos"]["items"][0]["text"] == "Implement sandbox"
    assert report["todo_changes"]
