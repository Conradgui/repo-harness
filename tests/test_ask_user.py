from repo_harness import FakeModelClient, RepoHarness, SessionStore, WorkspaceContext


def build_agent(tmp_path, outputs, **kwargs):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    return RepoHarness(
        model_client=FakeModelClient(outputs),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".repo-harness" / "sessions"),
        approval_policy="auto",
        **kwargs,
    )


def test_ask_user_tool_uses_callback_and_records_answer(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            '<tool>{"name":"ask_user","args":{"question":"Ship?","choices":["no","yes"]}}</tool>',
            "<final>Recorded.</final>",
        ],
        ask_user_callback=lambda question, choices: choices[-1],
    )

    assert agent.ask("ask before shipping") == "Recorded."
    tool_entries = [item for item in agent.session["history"] if item.get("role") == "tool"]
    assert tool_entries[-1]["name"] == "ask_user"
    assert "yes" in tool_entries[-1]["content"]


def test_plan_mode_allows_ask_user_tool(tmp_path):
    agent = build_agent(tmp_path, [], ask_user_callback=lambda question, choices: "staging")
    agent.enter_plan_mode("release")

    result = agent.run_tool("ask_user", {"question": "Which release?", "choices": ["staging", "prod"]})

    assert "staging" in result
