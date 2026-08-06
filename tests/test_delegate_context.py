"""The delegated child receives only the parent's explicit task, not its history.

The child context must stay clean: it gets the task the parent asks it to do,
and nothing else from the parent's conversation. Leaking parent history into
the child's notes is the exact opposite of "the child only receives what the
parent gives it" -- the child would inherit context it was not meant to see.

This pins the injection surface of tool_delegate: `task` yes, parent history
no.
"""

from unittest.mock import patch

from tests.conftest import build_agent


def _capture_child(tmp_path, task):
    """Run tool_delegate with RepoHarness construction captured."""
    agent = build_agent(tmp_path, [])
    captured = {}

    class ChildStub:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs
            captured["instance"] = self
            self.session = {"memory": {}}
            self.depth = 0
            self.max_depth = 10

        def ask(self, user_message):
            captured["ask_input"] = user_message
            return "delegate result"

    with patch("repo_harness.runtime.RepoHarness", ChildStub):
        result = agent.tool_delegate({"task": task, "max_steps": 2})

    assert result.startswith("delegate_result:")
    return captured, agent


def test_delegate_injects_task_but_not_parent_history(tmp_path):
    # Give the parent a non-trivial history so leakage would be visible.
    agent = build_agent(tmp_path, [])
    agent.session["history"] = [
        {"role": "user", "content": "secret setup detail: the token is abc-123"},
        {"role": "assistant", "content": "I looked into the routing layer."},
    ]

    captured = {}

    class ChildStub:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs
            captured["instance"] = self
            self.session = {"memory": {}}
            self.depth = 0
            self.max_depth = 10

        def ask(self, user_message):
            return "delegate result"

    with patch("repo_harness.runtime.RepoHarness", ChildStub):
        agent.tool_delegate({"task": "inspect the routing layer", "max_steps": 2})

    memory = captured["instance"].session["memory"]
    # The explicit task is the parent's control signal and must be present.
    assert memory.get("task") == "inspect the routing layer"
    # Parent history must NOT be injected as notes -- the child only sees
    # what the parent explicitly gives it.
    notes = memory.get("notes", [])
    assert not any("secret setup detail" in str(note) for note in notes)


def test_delegate_child_has_no_notes_without_parent_history(tmp_path):
    captured, _ = _capture_child(tmp_path, "inspect README.md")

    notes = captured["instance"].session["memory"].get("notes", [])
    # Empty history must not produce a leaked "- empty" marker either.
    assert notes == []
