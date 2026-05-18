from repo_harness import FakeModelClient, RepoHarness, SessionStore, WorkspaceContext
from repo_harness.core import tool_executor as core_tool_executor


def test_runtime_run_tool_delegates_to_core_executor(monkeypatch, tmp_path):
    agent = RepoHarness(
        model_client=FakeModelClient([]),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".repo-harness" / "sessions"),
        approval_policy="auto",
    )
    calls = []

    def fake_run_tool(runtime, name, args):
        calls.append((runtime, name, args))
        return "delegated"

    monkeypatch.setattr(core_tool_executor, "run_tool", fake_run_tool)

    assert agent.run_tool("read_file", {"path": "README.md"}) == "delegated"
    assert calls == [(agent, "read_file", {"path": "README.md"})]
