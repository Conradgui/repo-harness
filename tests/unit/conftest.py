"""Unit test fixtures for RepoHarness quality tests.

All tests use FakeModelClient or scripted providers.
No real API calls are made.
"""

import json
import os
from pathlib import Path

import pytest

from repo_harness import FakeModelClient, RepoHarness, SessionStore, WorkspaceContext


# ---------------------------------------------------------------------------
# Workspace helpers
# ---------------------------------------------------------------------------

def build_workspace(tmp_path, extra_files=None):
    """Create a minimal workspace context for testing.

    Args:
        tmp_path: pytest tmp_path fixture
        extra_files: optional dict of {relative_path: content} to add
    """
    (tmp_path / "README.md").write_text("# Test Project\n\nA demo project.\n", encoding="utf-8")
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "main.py").write_text(
        'def greet(name):\n    return f"Hello, {name}"\n',
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "tests" / "test_main.py").write_text(
        'from src.main import greet\n\ndef test_greet():\n    assert greet("World") == "Hello, World"\n',
        encoding="utf-8",
    )
    if extra_files:
        for rel_path, content in extra_files.items():
            p = tmp_path / rel_path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
    return WorkspaceContext.build(tmp_path)


def build_agent(tmp_path, outputs, extra_files=None, **kwargs):
    """Create a RepoHarness agent for testing with FakeModelClient.

    Args:
        tmp_path: pytest tmp_path fixture
        outputs: list of scripted model outputs for FakeModelClient
        extra_files: optional dict of {relative_path: content}
        **kwargs: additional kwargs passed to RepoHarness
    """
    workspace = build_workspace(tmp_path, extra_files=extra_files)
    store = SessionStore(tmp_path / ".repo-harness" / "sessions")
    approval_policy = kwargs.pop("approval_policy", "auto")
    return RepoHarness(
        model_client=FakeModelClient(outputs),
        workspace=workspace,
        session_store=store,
        approval_policy=approval_policy,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def workspace(tmp_path):
    """Minimal workspace context."""
    return build_workspace(tmp_path)


@pytest.fixture
def agent(tmp_path):
    """Basic RepoHarness agent with empty outputs."""
    return build_agent(tmp_path, [])


@pytest.fixture
def agent_with_file(tmp_path):
    """Agent with a readable source file."""
    return build_agent(tmp_path, [], extra_files={
        "src/utils.py": "def add(a, b):\n    return a + b\n",
    })


@pytest.fixture
def session_dir(tmp_path):
    """Return the session directory path (created by agent)."""
    return tmp_path / ".repo-harness" / "sessions"


@pytest.fixture
def memory_dir(tmp_path):
    """Return the memory directory path."""
    return tmp_path / ".repo-harness" / "memory"
