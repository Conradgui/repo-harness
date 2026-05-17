from repo_harness import FakeModelClient, RepoHarness, SessionStore, WorkspaceContext
from repo_harness.tui import RepoHarnessTuiApp


def test_tui_smoke_snapshot_without_textual(tmp_path):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    agent = RepoHarness(
        model_client=FakeModelClient([]),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".repo-harness" / "sessions"),
        approval_policy="auto",
    )
    agent.todo_ledger.add("Check TUI")

    app = RepoHarnessTuiApp(agent)
    snapshot = app.snapshot()

    assert "RepoHarness TUI" in snapshot
    assert agent.session["id"] in snapshot
    assert "Check TUI" in snapshot
