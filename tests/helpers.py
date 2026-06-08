"""Shared test helpers for RepoHarness tests."""

import os
import subprocess
import sys

import pytest

from repo_harness import FakeModelClient, RepoHarness, SessionStore, WorkspaceContext


def load_authorized_env(names=("DEEPSEEK_API_KEY", "MIMO_API_KEY")):
    """Load API keys from user/machine env scopes when PowerShell did not inherit them."""
    if sys.platform != "win32":
        return
    try:
        for name in names:
            if os.environ.get(name):
                continue
            script = (
                f"$v=[Environment]::GetEnvironmentVariable('{name}','User'); "
                f"if (-not $v) {{ $v=[Environment]::GetEnvironmentVariable('{name}','Machine') }}; "
                "$v"
            )
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            value = (completed.stdout or "").strip()
            if value:
                os.environ[name] = value
    except Exception:
        pass


def build_workspace(tmp_path, extra_files=None):
    """Create a minimal workspace context for testing."""
    (tmp_path / "README.md").write_text("# Test Project\n\nA demo project.\n", encoding="utf-8")
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "main.py").write_text(
        'def greet(name):\n    return f"Hello, {name}"\n',
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "tests" / "test_main.py").write_text(
        'from src.main import greet\n\n'
        'def test_greet():\n'
        '    assert greet("World") == "Hello, World"\n',
        encoding="utf-8",
    )
    if extra_files:
        for rel_path, content in extra_files.items():
            path = tmp_path / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    return WorkspaceContext.build(tmp_path)


def build_agent(tmp_path, outputs, extra_files=None, **kwargs):
    """Create a RepoHarness agent for testing with FakeModelClient."""
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


@pytest.fixture
def workspace(tmp_path):
    """Pytest fixture: minimal workspace context."""
    return build_workspace(tmp_path)


@pytest.fixture
def agent(tmp_path):
    """Pytest fixture: basic RepoHarness agent with empty outputs."""
    return build_agent(tmp_path, [])
