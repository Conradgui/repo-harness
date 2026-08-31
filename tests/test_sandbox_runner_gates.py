"""Wiring and configuration precedence for the sandbox.

The read_only decision in SandboxRunner has survived every direct attack. What
kept failing is the layer above it: an entry point that never passed the
sandbox config, and a configuration path where untrusted repository content
outranked the operator. These tests exercise the wiring rather than the
decision.
"""

from argparse import Namespace

import pytest

from repo_harness.config import resolve_runtime_config, sandbox_config_for_directory
from repo_harness.workspace import WorkspaceContext

TOML_READ_ONLY = '[sandbox]\nmode = "read_only"\n'


def _workspace(tmp_path, *, toml=None, env=None):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    if toml is not None:
        (tmp_path / ".repo-harness.toml").write_text(toml, encoding="utf-8")
    if env is not None:
        (tmp_path / ".env").write_text(env, encoding="utf-8")
    return WorkspaceContext.build(tmp_path)


def _args(tmp_path):
    return Namespace(
        cwd=str(tmp_path), config=None, provider=None, model=None, base_url=None,
        max_steps=None, max_new_tokens=None, sandbox=None, sandbox_backend=None,
    )


class TestConfigPrecedence:
    def test_a_repository_env_file_cannot_relax_the_sandbox(self, tmp_path, monkeypatch):
        """Untrusted repository content must not decide its own isolation level.

        _effective_env merges the repo's .env so provider settings can live
        there. Reading that merged dict for the sandbox mode let a cloned repo
        ship REPO_HARNESS_SANDBOX=off and override both its own
        .repo-harness.toml and the operator's global config.
        """
        monkeypatch.delenv("REPO_HARNESS_SANDBOX", raising=False)
        workspace = _workspace(
            tmp_path, toml=TOML_READ_ONLY, env="REPO_HARNESS_SANDBOX=off\n"
        )

        resolved = resolve_runtime_config(_args(tmp_path), workspace)

        assert resolved.sandbox.mode == "read_only"

    def test_a_repository_env_file_cannot_change_the_backend_either(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.delenv("REPO_HARNESS_SANDBOX_BACKEND", raising=False)
        workspace = _workspace(
            tmp_path,
            toml='[sandbox]\nmode = "required"\nbackend = "bubblewrap"\n',
            env="REPO_HARNESS_SANDBOX_BACKEND=native\n",
        )

        resolved = resolve_runtime_config(_args(tmp_path), workspace)

        assert resolved.sandbox.backend == "bubblewrap"

    def test_the_real_environment_may_still_relax_the_sandbox(self, tmp_path, monkeypatch):
        """The operator's own shell keeps its override; only the repo's .env loses it."""
        monkeypatch.setenv("REPO_HARNESS_SANDBOX", "best_effort")
        workspace = _workspace(tmp_path, toml=TOML_READ_ONLY)

        resolved = resolve_runtime_config(_args(tmp_path), workspace)

        assert resolved.sandbox.mode == "best_effort"

    def test_the_toml_declaration_is_honoured_when_nothing_overrides_it(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.delenv("REPO_HARNESS_SANDBOX", raising=False)
        workspace = _workspace(tmp_path, toml=TOML_READ_ONLY)

        assert resolve_runtime_config(_args(tmp_path), workspace).sandbox.mode == "read_only"


class TestDirectoryHelper:
    def test_reads_the_declaration_from_a_directory(self, tmp_path):
        (tmp_path / ".repo-harness.toml").write_text(TOML_READ_ONLY, encoding="utf-8")

        assert sandbox_config_for_directory(tmp_path).mode == "read_only"

    def test_defaults_to_off_without_a_declaration(self, tmp_path):
        assert sandbox_config_for_directory(tmp_path).mode == "off"

    def test_ignores_the_ambient_environment(self, tmp_path, monkeypatch):
        """A clone's isolation must not depend on the shell that cloned it."""
        monkeypatch.setenv("REPO_HARNESS_SANDBOX", "off")
        (tmp_path / ".repo-harness.toml").write_text(TOML_READ_ONLY, encoding="utf-8")

        assert sandbox_config_for_directory(tmp_path).mode == "read_only"


class TestAutoIssueFixWiring:
    def test_the_clone_declaration_reaches_the_agent(self, tmp_path, monkeypatch):
        """Assert on what runner.py passes, not on what the helper returns.

        The bug was that runner.py never called the helper. A test that only
        checked the helper stayed green with the fix removed.
        """
        from repo_harness.auto_issue_fix import runner as aif_runner
        from repo_harness.auto_issue_fix.config import (
            AutoIssueFixConfig,
            AutoIssueFixIssue,
        )

        (tmp_path / ".repo-harness.toml").write_text(TOML_READ_ONLY, encoding="utf-8")
        seen = {}

        class FakeAgent:
            def __init__(self, **kwargs):
                seen.update(kwargs)

            def ask(self, prompt):
                del prompt
                return "done"

        monkeypatch.setattr("repo_harness.runtime.RepoHarness", FakeAgent)

        aif_runner.run_repoharness_fix_turn(
            AutoIssueFixConfig(repo="owner/name", issue=1),
            AutoIssueFixIssue(
                repo="owner/name", number=1, title="t", body="b", url="u"
            ),
            tmp_path,
            model_client=object(),
        )

        assert "sandbox_config" in seen, (
            "run_repoharness_fix_turn must pass the clone's sandbox declaration"
        )
        assert seen["sandbox_config"].mode == "read_only"

    def test_a_clone_without_a_declaration_gets_the_restricted_default(self, tmp_path, monkeypatch):
        """An undeclared clone fails safe: the restricted sandbox default applies.

        The old assertion locked in mode "off" as the expected default for
        Auto Issue Fix clones -- the finding called this out directly: a
        high-quality test locking in an unsafe default value.
        """
        from repo_harness.auto_issue_fix import runner as aif_runner
        from repo_harness.auto_issue_fix.config import (
            AutoIssueFixConfig,
            AutoIssueFixIssue,
        )

        seen = {}

        class FakeAgent:
            def __init__(self, **kwargs):
                seen.update(kwargs)

            def ask(self, prompt):
                del prompt
                return "done"

        monkeypatch.setattr("repo_harness.runtime.RepoHarness", FakeAgent)

        aif_runner.run_repoharness_fix_turn(
            AutoIssueFixConfig(repo="owner/name", issue=1),
            AutoIssueFixIssue(
                repo="owner/name", number=1, title="t", body="b", url="u"
            ),
            tmp_path,
            model_client=object(),
        )

        assert seen["sandbox_config"].mode == "required"
        assert seen["sandbox_config"].backend == "bubblewrap"


@pytest.mark.parametrize("mode", ["READ_ONLY", "Read_Only", "readonly", "typo", ""])
def test_a_misspelled_mode_never_reaches_execution(tmp_path, mode):
    """A config typo must fail closed, not fall through to "run it".

    Mode validation used to happen after the exemption, so READ_ONLY in a
    config file reached the matcher and an exempted command ran on the host.
    """
    from repo_harness.sandbox import SandboxConfig, SandboxRunner

    runner = SandboxRunner(
        SandboxConfig(mode=mode, backend="native", excluded_commands=("git status*",))
    )

    def must_not_run(command, timeout):
        raise AssertionError(f"reached the platform runner: {command!r}")

    if mode == "":
        # An empty mode is the documented default, not a typo.
        assert runner.run(None, "git status", 20, must_not_run) is None
    else:
        with pytest.raises(RuntimeError, match="unsupported sandbox mode"):
            runner.run(None, "git status", 20, must_not_run)
