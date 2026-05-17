from unittest.mock import patch

from repo_harness import FakeModelClient, RepoHarness, SessionStore, WorkspaceContext
from repo_harness import cli as mini_cli


def build_agent(tmp_path, outputs=None):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    workspace = WorkspaceContext.build(tmp_path)
    return RepoHarness(
        model_client=FakeModelClient(outputs or []),
        workspace=workspace,
        session_store=SessionStore(tmp_path / ".repo-harness" / "sessions"),
        approval_policy="auto",
    )


def test_discovers_project_and_repo_harness_skills(tmp_path):
    (tmp_path / "skills" / "inspect" ).mkdir(parents=True)
    (tmp_path / "skills" / "inspect" / "SKILL.md").write_text(
        "---\nname: inspect\ndescription: Inspect code safely\n---\nUse read_file before edits.\n",
        encoding="utf-8",
    )
    (tmp_path / ".repo-harness" / "skills" / "handoff").mkdir(parents=True)
    (tmp_path / ".repo-harness" / "skills" / "handoff" / "SKILL.md").write_text(
        "---\nname: handoff\ndescription: Prepare handoff\n---\nSummarize current state.\n",
        encoding="utf-8",
    )

    agent = build_agent(tmp_path)

    assert set(agent.skills) >= {"inspect", "handoff"}
    listing = agent.render_skills()
    assert "inspect" in listing
    assert "Prepare handoff" in listing


def test_skill_invocation_is_review_queue_safe(tmp_path):
    (tmp_path / "skills" / "rememberish").mkdir(parents=True)
    (tmp_path / "skills" / "rememberish" / "SKILL.md").write_text(
        "---\nname: rememberish\ndescription: Mentions memory\n---\nProject convention: Never auto-write durable memory.\n",
        encoding="utf-8",
    )
    agent = build_agent(tmp_path)

    result = agent.invoke_skill("rememberish", "now")

    assert "Never auto-write durable memory" in result
    assert not (tmp_path / ".repo-harness" / "memory" / "topics").exists()
    assert not (tmp_path / ".repo-harness" / "memory" / "review-queue.jsonl").exists()


def test_repl_skills_and_skill_commands_do_not_call_model(tmp_path, capsys):
    (tmp_path / "skills" / "inspect").mkdir(parents=True)
    (tmp_path / "skills" / "inspect" / "SKILL.md").write_text(
        "---\nname: inspect\ndescription: Inspect code safely\n---\nUse constrained tools.\n",
        encoding="utf-8",
    )
    agent = build_agent(tmp_path)

    with patch("repo_harness.cli.build_agent", return_value=agent), patch(
        "repo_harness.cli.build_welcome",
        return_value="welcome",
    ), patch("builtins.input", side_effect=["/skills", "/skill inspect README.md", "/exit"]):
        result = mini_cli.main(["--cwd", str(tmp_path)])

    assert result == 0
    output = capsys.readouterr().out
    assert "inspect" in output
    assert "Use constrained tools." in output
    assert agent.model_client.prompts == []
