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


def test_tui_slash_suggestions_and_runtime_event_flow(tmp_path):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    agent = RepoHarness(
        model_client=FakeModelClient(["<final>Hello TUI.</final>"]),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".repo-harness" / "sessions"),
        approval_policy="auto",
    )
    app = RepoHarnessTuiApp(agent)

    assert "skills" in [item.name for item in app.suggest_commands("/sk")]
    events = list(app.run_turn("hello"))

    assert events[-1]["type"] == "final"
    assert "Hello TUI." in app.snapshot()


def test_tui_ask_user_prompt_records_choice(tmp_path):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    agent = RepoHarness(
        model_client=FakeModelClient([
            '<tool>{"name":"ask_user","args":{"question":"Ship?","choices":["no","yes"]}}</tool>',
            "<final>done</final>",
        ]),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".repo-harness" / "sessions"),
        approval_policy="auto",
    )
    app = RepoHarnessTuiApp(agent)
    app.ask_user_answers.append("yes")

    assert list(app.run_turn("ask"))[-1]["content"] == "done"
    assert "yes" in agent.session["history"][-2]["content"]
