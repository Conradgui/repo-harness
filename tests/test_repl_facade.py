"""Tests for the REPL facade."""

from repo_harness import FakeModelClient, RepoHarness, SessionStore, WorkspaceContext
from repo_harness.repl_facade import ReplFacade


def test_repl_facade_snapshot(tmp_path):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    agent = RepoHarness(
        model_client=FakeModelClient([]),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".repo-harness" / "sessions"),
        approval_policy="auto",
    )
    agent.todo_ledger.add("Check REPL")

    facade = ReplFacade(agent)
    snapshot = facade.snapshot()

    assert "RepoHarness" in snapshot
    assert agent.session["id"] in snapshot
    assert "Check REPL" in snapshot


def test_repl_facade_slash_suggestions_and_run_turn(tmp_path):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    agent = RepoHarness(
        model_client=FakeModelClient(["<final>Hello REPL.</final>"]),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".repo-harness" / "sessions"),
        approval_policy="auto",
    )
    facade = ReplFacade(agent)

    assert "skills" in [item.name for item in facade.suggest_commands("/sk")]
    events = list(facade.run_turn("hello"))

    assert events[-1]["type"] == "final"
    assert "Hello REPL." in facade.snapshot()


def test_repl_facade_ask_user_prompt_records_choice(tmp_path):
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
    facade = ReplFacade(agent)
    facade.ask_user_answers.append("yes")

    assert list(facade.run_turn("ask"))[-1]["content"] == "done"
    assert "yes" in agent.session["history"][-2]["content"]
