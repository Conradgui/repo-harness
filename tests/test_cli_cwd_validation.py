"""--cwd pointing at a missing directory must fail loudly, not silently run
in a phantom workspace.

A user who typos --cwd (or points at a deleted directory) would otherwise get
an agent that claims a clean workspace in a path that does not exist, and any
file writes land in the wrong place. Diagnostic commands (provider probe /
doctor / setup) intentionally do not use this assembly path, so they are
unaffected.
"""

from argparse import Namespace

import pytest

from repo_harness.cli import build_agent


def _args(cwd):
    return Namespace(
        cwd=cwd,
        provider="deepseek",
        model="deepseek-v4-pro",
        base_url="https://api.deepseek.com/anthropic",
        config=None,
        host=None,
        temperature=0.2,
        top_p=0.9,
        ollama_timeout=300,
        openai_timeout=300,
        max_steps=50,
        max_new_tokens=8192,
        sandbox=None,
        sandbox_backend=None,
        secret_env_names=(),
        approval="auto",
        trust_session=False,
        resume=None,
    )


def test_build_agent_rejects_missing_cwd(tmp_path):
    missing = tmp_path / "does_not_exist_xyz"
    with pytest.raises(ValueError, match="does not exist"):
        build_agent(_args(str(missing)))


def test_build_agent_accepts_existing_cwd(tmp_path):
    # Sanity: a real directory still assembles (the model client build may
    # fail later for other reasons, but the cwd check itself must pass).
    try:
        agent = build_agent(_args(str(tmp_path)))
        assert agent is not None
    except ValueError as exc:
        pytest.fail(f"existing cwd must not raise ValueError: {exc}")
