"""Contract for the tools that change the workspace.

write_file and patch_file are the reason this project exists -- an agent that
cannot modify a repository is a read-only question answerer. They were covered
only end-to-end, which proves they work in the happy path but pins none of the
boundaries: what happens on a path outside the repository, on a directory that
does not exist yet, or when the text to replace appears twice.

run_shell is the other tool that reaches outside the process. Its contract is
that it reports a failing command rather than raising, and that it never hands
the child process the parent's full environment.
"""

import pytest
from conftest import build_agent

from repo_harness import tools


@pytest.fixture
def agent(tmp_path):
    return build_agent(tmp_path, [], approval_policy="auto")


class TestWriteFile:
    def test_writes_utf8_and_reports_the_relative_path(self, agent, tmp_path):
        result = tools.tool_write_file(agent, {"path": "notes.md", "content": "你好\n"})

        assert (tmp_path / "notes.md").read_text(encoding="utf-8") == "你好\n"
        assert "notes.md" in result

    def test_creates_missing_parent_directories(self, agent, tmp_path):
        tools.tool_write_file(agent, {"path": "a/b/c/deep.txt", "content": "x"})

        assert (tmp_path / "a" / "b" / "c" / "deep.txt").read_text(encoding="utf-8") == "x"

    def test_overwrites_an_existing_file(self, agent, tmp_path):
        (tmp_path / "f.txt").write_text("old", encoding="utf-8")

        tools.tool_write_file(agent, {"path": "f.txt", "content": "new"})

        assert (tmp_path / "f.txt").read_text(encoding="utf-8") == "new"

    @pytest.mark.parametrize("escape", ["../outside.txt", "../../outside.txt"])
    def test_refuses_to_write_outside_the_workspace(self, agent, tmp_path, escape):
        with pytest.raises(ValueError, match="escapes workspace"):
            tools.tool_write_file(agent, {"path": escape, "content": "x"})

        assert not (tmp_path.parent / "outside.txt").exists()

    def test_reported_length_is_the_content_length(self, agent):
        result = tools.tool_write_file(agent, {"path": "n.txt", "content": "abcde"})

        assert "5 chars" in result


class TestPatchFile:
    @pytest.fixture
    def target(self, tmp_path):
        path = tmp_path / "code.py"
        path.write_text("def f():\n    return -1\n", encoding="utf-8")
        return path

    def test_replaces_a_unique_block(self, agent, target):
        tools.tool_patch_file(
            agent, {"path": "code.py", "old_text": "return -1", "new_text": "return 0"}
        )

        assert target.read_text(encoding="utf-8") == "def f():\n    return 0\n"

    def test_refuses_when_the_old_text_appears_twice(self, agent, tmp_path):
        path = tmp_path / "twice.py"
        path.write_text("x = 1\nx = 1\n", encoding="utf-8")

        with pytest.raises(ValueError, match="exactly once, found 2"):
            tools.tool_patch_file(
                agent, {"path": "twice.py", "old_text": "x = 1", "new_text": "x = 2"}
            )

        # An ambiguous patch must change nothing at all.
        assert path.read_text(encoding="utf-8") == "x = 1\nx = 1\n"

    def test_refuses_when_the_old_text_is_absent(self, agent, target):
        with pytest.raises(ValueError, match="exactly once, found 0"):
            tools.tool_patch_file(
                agent, {"path": "code.py", "old_text": "nope", "new_text": "x"}
            )

        assert "return -1" in target.read_text(encoding="utf-8")

    def test_rejects_an_empty_old_text(self, agent, target):
        with pytest.raises(ValueError, match="old_text must not be empty"):
            tools.tool_patch_file(agent, {"path": "code.py", "old_text": "", "new_text": "x"})

    def test_requires_new_text_to_be_present(self, agent, target):
        # Missing and empty are different: an empty new_text is a deletion.
        with pytest.raises(ValueError, match="missing new_text"):
            tools.tool_patch_file(agent, {"path": "code.py", "old_text": "return -1"})

    def test_empty_new_text_deletes_the_block(self, agent, target):
        tools.tool_patch_file(
            agent, {"path": "code.py", "old_text": "    return -1\n", "new_text": ""}
        )

        assert target.read_text(encoding="utf-8") == "def f():\n"

    def test_refuses_a_directory(self, agent, tmp_path):
        (tmp_path / "adir").mkdir()

        with pytest.raises(ValueError, match="path is not a file"):
            tools.tool_patch_file(
                agent, {"path": "adir", "old_text": "a", "new_text": "b"}
            )

    def test_refuses_to_patch_outside_the_workspace(self, agent, tmp_path):
        outside = tmp_path.parent / "outside.py"
        outside.write_text("secret", encoding="utf-8")
        try:
            with pytest.raises(ValueError, match="escapes workspace"):
                tools.tool_patch_file(
                    agent,
                    {"path": "../outside.py", "old_text": "secret", "new_text": "leaked"},
                )
            assert outside.read_text(encoding="utf-8") == "secret"
        finally:
            outside.unlink()


class TestRunShellValidation:
    """Argument validation, which happens before anything is executed."""

    def test_rejects_an_empty_command(self, agent):
        with pytest.raises(ValueError, match="command must not be empty"):
            tools.tool_run_shell(agent, {"command": "   "})

    @pytest.mark.parametrize("timeout", [0, -1, 601, 9999])
    def test_rejects_a_timeout_outside_the_allowed_range(self, agent, timeout):
        with pytest.raises(ValueError, match=r"timeout must be in \[1, 600\]"):
            tools.tool_run_shell(agent, {"command": "echo hi", "timeout": timeout})


class TestShellSandboxGate:
    """read_only sandbox mode is a permission decision, not only a raise.

    SandboxRunner also raises for this, which reaches the model as a generic
    tool failure. Deciding it in PermissionChecker means the refusal carries a
    reason and appears in the permission matrix alongside every other gate.
    """

    @pytest.mark.parametrize("mode", ["off", "best_effort"])
    def test_shell_is_allowed_when_the_sandbox_does_not_block_it(self, tmp_path, mode):
        from repo_harness.sandbox import SandboxConfig

        agent = build_agent(
            tmp_path, [], approval_policy="auto", sandbox_config=SandboxConfig(mode=mode)
        )

        decision = agent.permission_checker.check("run_shell", {"command": "echo hi"})

        assert decision.decision == "allow"

    def test_read_only_mode_denies_shell_with_a_reason(self, tmp_path):
        from repo_harness.sandbox import SandboxConfig

        agent = build_agent(
            tmp_path,
            [],
            approval_policy="auto",
            sandbox_config=SandboxConfig(mode="read_only"),
        )

        decision = agent.permission_checker.check("run_shell", {"command": "echo hi"})

        assert decision.decision == "deny"
        assert decision.reason == "sandbox_read_only"
        assert decision.security_event_type == "sandbox_guard"

    @pytest.mark.parametrize(
        "command",
        [
            "git status",                      # matches the pattern exactly
            "git status; rm -rf x",            # chaining
            "git status %X%",                  # cmd.exe expansion
            "git status/../whoami",            # git dashed-external dispatch
            "git statusx/../whoami",
        ],
    )
    def test_read_only_has_no_exemption(self, tmp_path, command):
        """No command runs under read_only, whatever excluded_commands says.

        The exemption used to apply here, and making it safe required deciding
        from a command string that the command can only do one thing. Three
        rounds of filtering were each defeated; `git status/../whoami` carries
        no shell metacharacter at all and still runs an arbitrary program. See
        ADR-007.
        """
        from repo_harness.sandbox import SandboxConfig

        agent = build_agent(
            tmp_path,
            [],
            approval_policy="auto",
            sandbox_config=SandboxConfig(
                mode="read_only", excluded_commands=("git status*",)
            ),
        )

        decision = agent.permission_checker.check("run_shell", {"command": command})

        assert decision.decision == "deny"
        assert decision.reason == "sandbox_read_only"

    def test_the_exemption_still_applies_outside_read_only(self, tmp_path):
        """best_effort keeps it -- that mode never promised isolation."""
        from repo_harness.sandbox import SandboxConfig, SandboxRunner

        runner = SandboxRunner(
            SandboxConfig(mode="best_effort", excluded_commands=("git status*",))
        )

        assert runner._command_is_excluded("git status --short") is True
        assert runner._command_is_excluded("git status; rm -rf x") is False

    def test_read_only_mode_does_not_block_reading(self, tmp_path):
        from repo_harness.sandbox import SandboxConfig

        agent = build_agent(
            tmp_path,
            [],
            approval_policy="auto",
            sandbox_config=SandboxConfig(mode="read_only"),
        )

        assert agent.permission_checker.check("read_file", {"path": "README.md"}).decision == "allow"
        assert agent.permission_checker.check("search", {"pattern": "x"}).decision == "allow"


class TestShellEnvironment:
    """The child process must not inherit the parent's environment wholesale."""

    def test_secret_shaped_variables_are_not_passed_through(self, agent, monkeypatch):
        monkeypatch.setenv("MY_SERVICE_API_KEY", "sk-should-not-leak")

        env = agent.shell_env()

        assert "MY_SERVICE_API_KEY" not in env or env["MY_SERVICE_API_KEY"] != "sk-should-not-leak"

    def test_path_is_present_so_commands_can_be_found(self, agent):
        assert "PATH" in agent.shell_env()
