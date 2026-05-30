"""Shared test helpers for repo_harness tests."""

import pytest

from repo_harness import FakeModelClient, RepoHarness, SessionStore, WorkspaceContext


def build_workspace(tmp_path):
    """Create a minimal workspace context for testing."""
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    return WorkspaceContext.build(tmp_path)


def build_agent(tmp_path, outputs, **kwargs):
    """Create a RepoHarness agent for testing with FakeModelClient.

    Args:
        tmp_path: pytest tmp_path fixture
        outputs: list of scripted model outputs for FakeModelClient
        **kwargs: additional kwargs passed to RepoHarness (e.g. approval_policy, read_only)
    """
    workspace = build_workspace(tmp_path)
    store = SessionStore(tmp_path / ".repo-harness" / "sessions")
    approval_policy = kwargs.pop("approval_policy", "auto")
    return RepoHarness(
        model_client=FakeModelClient(outputs),
        workspace=workspace,
        session_store=store,
        approval_policy=approval_policy,
        **kwargs,
    )


@pytest.fixture
def workspace(tmp_path):
    """Pytest fixture: minimal workspace context."""
    return build_workspace(tmp_path)


@pytest.fixture
def agent(tmp_path):
    """Pytest fixture: basic RepoHarness agent with empty outputs."""
    return build_agent(tmp_path, [])
