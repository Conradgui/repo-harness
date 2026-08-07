"""Auto Issue Fix must honour a cloned repository's declared read_only sandbox.

sandbox_config_for_directory reads the clone's .repo-harness.toml. If it
declares `sandbox = "read_only"`, the agent must be read-only for ALL tools
(including write_file / patch_file), not just run_shell -- otherwise the
repository's own declared boundary is silently bypassed for file writes,
violating the fail-closed principle (ADR-002/007).
"""

from repo_harness.auto_issue_fix.config import AutoIssueFixConfig, AutoIssueFixIssue
from repo_harness.auto_issue_fix.runner import run_repoharness_fix_turn


class _FakeModel:
    """Stand-in model client so tests never depend on a real provider build."""

    def complete(self, *args, **kwargs):
        raise AssertionError("model should not be called in these tests")


def _issue():
    return AutoIssueFixIssue(
        repo="local/fixture",
        number=1,
        title="sample issue",
        body="sample body",
        url="https://github.com/local/fixture/issues/1",
    )


def _config(tmp_path):
    return AutoIssueFixConfig(
        repo="local/fixture",
        issue=1,
        workspace_root=tmp_path,
        mode="draft-auto",
        maintainer_access_confirmed=True,
    )


def test_declared_read_only_clone_makes_fix_turn_read_only(tmp_path, monkeypatch):
    # Clone declares read_only via its .repo-harness.toml.
    (tmp_path / ".repo-harness.toml").write_text(
        '[sandbox]\nmode = "read_only"\n', encoding="utf-8"
    )
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")

    captured = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

        def ask(self, prompt):
            return "fix done"

    monkeypatch.setattr("repo_harness.runtime.RepoHarness", FakeAgent)

    run_repoharness_fix_turn(
        _config(tmp_path),
        _issue(),
        tmp_path,
        model_client=_FakeModel(),
        workspace_root=tmp_path,
    )

    kwargs = captured["kwargs"]
    # read_only must be True so approve() rejects write_file/patch_file.
    assert kwargs.get("read_only") is True, (
        "a clone that declares sandbox=read_only must run the fix turn read-only; "
        f"got read_only={kwargs.get('read_only')}"
    )
    # And the sandbox config must be the declared read_only one, not default off.
    assert kwargs.get("sandbox_config").mode == "read_only"


def test_default_clone_keeps_fix_turn_writable(tmp_path, monkeypatch):
    # A normal clone (no sandbox declaration) must stay writable so fixes work.
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")

    captured = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

        def ask(self, prompt):
            return "fix done"

    monkeypatch.setattr("repo_harness.runtime.RepoHarness", FakeAgent)

    run_repoharness_fix_turn(
        _config(tmp_path),
        _issue(),
        tmp_path,
        model_client=_FakeModel(),
        workspace_root=tmp_path,
    )

    kwargs = captured["kwargs"]
    assert kwargs.get("read_only") is False, "a default clone must stay writable"
