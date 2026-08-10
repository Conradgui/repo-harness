"""One-shot execution under a non-interactive stdin must fail fast when the
approval policy is not auto.

Previously a one-shot run with the default approval=ask on a piped/CI stdin
ran the whole turn and silently denied every risky tool (EOF -> no answer),
leaving the user with "operations have been denied approval" and no hint. The
product now detects the non-interactive + non-auto combination up front and
returns an actionable error before building the agent.
"""

import sys
from unittest.mock import patch

from repo_harness.cli import main


class _NonInteractiveStdin:
    def isatty(self):
        return False


def test_oneshot_noninteractive_ask_fails_fast(monkeypatch):
    monkeypatch.setattr(sys, "stdin", _NonInteractiveStdin())

    with patch("repo_harness.repl_display.ReplDisplay") as fake_display:
        display_instance = fake_display.return_value
        # Use real argv so main() parses it; --approval defaults to ask.
        code = main(["do the task"])
        # build_agent must not even be reached: fail-fast happens first.
        assert code == 1
        display_instance.show_error.assert_called_once()
        error_text = display_instance.show_error.call_args.args[0]
        assert "--approval auto" in error_text


def test_oneshot_interactive_ask_proceeds(monkeypatch):
    # An interactive terminal with ask is allowed (approvals can be answered).
    class _InteractiveStdin:
        def isatty(self):
            return True

    monkeypatch.setattr(sys, "stdin", _InteractiveStdin())
    # It proceeds to build_agent (no fail-fast), then runs the turn.
    with patch("repo_harness.repl_display.ReplDisplay"):
        # build_agent is real here; with a fake model-free run it will try to
        # connect. We only assert no fail-fast happens by patching build_agent.
        with patch("repo_harness.cli.build_agent") as fake_build:
            agent = fake_build.return_value
            agent.engine.run_turn.return_value = iter(
                [{"type": "final", "content": "done"}]
            )
            code = main(["do the task"])
            fake_build.assert_called_once()
            assert code == 0


def test_oneshot_noninteractive_auto_proceeds(monkeypatch):
    monkeypatch.setattr(sys, "stdin", _NonInteractiveStdin())
    with patch("repo_harness.repl_display.ReplDisplay"):
        with patch("repo_harness.cli.build_agent") as fake_build:
            agent = fake_build.return_value
            agent.engine.run_turn.return_value = iter(
                [{"type": "final", "content": "done"}]
            )
            code = main(["--approval", "auto", "do the task"])
            fake_build.assert_called_once()
            assert code == 0


def test_oneshot_noninteractive_trust_session_proceeds(monkeypatch):
    # --trust-session is the fail-fast hint's own recommended option and is
    # equivalent to approval=auto inside build_agent; it must not be rejected.
    monkeypatch.setattr(sys, "stdin", _NonInteractiveStdin())
    with patch("repo_harness.repl_display.ReplDisplay"):
        with patch("repo_harness.cli.build_agent") as fake_build:
            agent = fake_build.return_value
            agent.engine.run_turn.return_value = iter(
                [{"type": "final", "content": "done"}]
            )
            code = main(["--trust-session", "do the task"])
            fake_build.assert_called_once()
            assert code == 0
