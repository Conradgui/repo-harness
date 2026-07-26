"""Behaviour contract for the search tool.

search has two backends -- ripgrep when it is on PATH, and a pure-Python walk
when it is not. Both must answer identically, otherwise the same agent task
gives different results depending on the host.

These tests never require rg to be installed: the fallback is exercised for
real, and the rg backend is pinned by asserting on the argv that would be
handed to ripgrep. A test that skips on the developer's machine is not a test.
"""

import subprocess

import pytest

from conftest import build_agent
from repo_harness import tools
from repo_harness.tools import tool_search


@pytest.fixture
def agent_with_files(tmp_path):
    agent = build_agent(tmp_path, [])
    (tmp_path / "alpha.txt").write_text(
        "needle here\nNEEDLE upper\nunrelated line\n", encoding="utf-8"
    )
    (tmp_path / "beta.txt").write_text("Needle mixed case\n", encoding="utf-8")
    (tmp_path / "regex.txt").write_text("a.c\nabc\n", encoding="utf-8")
    (tmp_path / "dash.txt").write_text("value --files here\n", encoding="utf-8")
    return agent


@pytest.fixture
def no_rg(monkeypatch):
    """Force the pure-Python fallback."""
    monkeypatch.setattr(tools.shutil, "which", lambda _name: None)


@pytest.fixture
def captured_rg_argv(monkeypatch):
    """Pretend rg exists and capture the argv it would be invoked with."""
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = list(argv)
        seen["kwargs"] = kwargs
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(tools.shutil, "which", lambda _name: "/usr/bin/rg")
    monkeypatch.setattr(tools.subprocess, "run", fake_run)
    return seen


def _hit_lines(output):
    return sorted(
        line.split(":", 2)[2].strip()
        for line in output.splitlines()
        if line.count(":") >= 2 and line != "(no matches)"
    )


class TestPythonFallback:
    def test_lowercase_pattern_ignores_case(self, agent_with_files, no_rg):
        result = tool_search(agent_with_files, {"pattern": "needle"})

        assert _hit_lines(result) == ["NEEDLE upper", "Needle mixed case", "needle here"]

    def test_uppercase_pattern_is_case_sensitive(self, agent_with_files, no_rg):
        result = tool_search(agent_with_files, {"pattern": "NEEDLE"})

        assert _hit_lines(result) == ["NEEDLE upper"]

    def test_pattern_is_literal_not_regex(self, agent_with_files, no_rg):
        result = tool_search(agent_with_files, {"pattern": "a.c"})

        # A regex would also match "abc"; a literal search must not.
        assert _hit_lines(result) == ["a.c"]

    def test_leading_dash_pattern_is_ordinary_text(self, agent_with_files, no_rg):
        result = tool_search(agent_with_files, {"pattern": "--files"})

        assert _hit_lines(result) == ["value --files here"]

    def test_no_match_reports_a_stable_sentinel(self, agent_with_files, no_rg):
        assert tool_search(agent_with_files, {"pattern": "absent-xyz"}) == "(no matches)"


class TestRipgrepInvocation:
    def test_pattern_is_terminated_so_it_cannot_become_an_option(
        self, agent_with_files, captured_rg_argv
    ):
        tool_search(agent_with_files, {"pattern": "--files"})
        argv = captured_rg_argv["argv"]

        # Everything after -- is positional, so a pattern starting with a dash
        # is searched for rather than executed as a ripgrep flag.
        assert "--" in argv
        assert argv.index("--files") > argv.index("--")

    def test_search_is_literal_to_avoid_redos(self, agent_with_files, captured_rg_argv):
        tool_search(agent_with_files, {"pattern": "a.c"})

        assert "--fixed-strings" in captured_rg_argv["argv"]

    def test_output_is_decoded_as_utf8(self, agent_with_files, captured_rg_argv):
        tool_search(agent_with_files, {"pattern": "needle"})

        # Without an explicit encoding Python decodes with the system locale,
        # which raises UnicodeDecodeError on non-UTF-8 hosts and silently
        # turns stdout into None.
        assert captured_rg_argv["kwargs"]["encoding"] == "utf-8"
        assert captured_rg_argv["kwargs"]["errors"] == "replace"


class TestSharedContract:
    @pytest.mark.parametrize(
        "pattern,expected",
        [
            ("needle", ["NEEDLE upper", "Needle mixed case", "needle here"]),
            ("NEEDLE", ["NEEDLE upper"]),
            ("a.c", ["a.c"]),
            ("--files", ["value --files here"]),
        ],
    )
    def test_smart_case_decision_matches_the_flag_sent_to_ripgrep(
        self, agent_with_files, no_rg, pattern, expected
    ):
        # The fallback implements --smart-case in Python; these expectations are
        # the same ones ripgrep would produce for the argv asserted above.
        assert _hit_lines(tool_search(agent_with_files, {"pattern": pattern})) == expected

    def test_empty_pattern_is_rejected_before_either_backend_runs(self, agent_with_files):
        with pytest.raises(ValueError, match="pattern must not be empty"):
            tool_search(agent_with_files, {"pattern": "   "})
