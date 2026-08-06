"""G2: blocked tool failures must escalate deterministically.

The product contract: on a blocked tool, the agent first tries a safe
alternative within its authority; if the same root cause keeps blocking and no
new information arrives, it asks the user. Escalation must be a structured
runtime decision, not a prompt-level hope.

Current behaviour lacks this: tool failures only return an error string to the
model, and no deterministic escalation exists. These tests fail until the
mechanism lands.
"""

from repo_harness import FakeModelClient, RepoHarness, SessionStore, WorkspaceContext


def build_agent(tmp_path, outputs, **kwargs):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    return RepoHarness(
        model_client=FakeModelClient(outputs),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".repo-harness" / "sessions"),
        approval_policy=kwargs.pop("approval_policy", "auto"),
        **kwargs,
    )


def _record_denial(agent, tool_error_code, tool, args):
    """Simulate a blocked tool call the way tool_executor records it."""
    agent._last_tool_result_metadata = {
        "tool_status": "rejected",
        "tool_error_code": tool_error_code,
        "affected_paths": [],
        "risk_level": "high",
        "read_only": False,
    }
    agent._record_runtime_reminder(tool, agent._last_tool_result_metadata)


def test_first_tool_failure_does_not_upgrade(tmp_path):
    agent = build_agent(tmp_path, [])
    _record_denial(agent, "tool_not_allowed", "write_file", {"path": "x.txt"})
    assert agent.evaluate_blocked_state() is None, "first failure must not upgrade"


def test_same_root_cause_repeated_upgrades(tmp_path):
    agent = build_agent(tmp_path, [])
    _record_denial(agent, "tool_not_allowed", "write_file", {"path": "x.txt"})
    _record_denial(agent, "tool_not_allowed", "write_file", {"path": "x.txt"})
    upgrade = agent.evaluate_blocked_state()
    assert upgrade is not None, "same root cause repeated with no new tool must upgrade"
    assert "tool_not_allowed" in upgrade["root_cause"]


def test_alternative_tool_counts_as_progress(tmp_path):
    agent = build_agent(tmp_path, [])
    _record_denial(agent, "tool_not_allowed", "write_file", {"path": "x.txt"})
    _record_denial(agent, "tool_not_allowed", "patch_file", {"path": "x.txt"})
    # A new tool name means the agent tried an alternative: delay the upgrade.
    assert agent.evaluate_blocked_state() is None


def test_irreplaceable_denial_upgrades_immediately(tmp_path):
    agent = build_agent(tmp_path, [])
    _record_denial(agent, "approval_denied", "write_file", {"path": "x.txt"})
    upgrade = agent.evaluate_blocked_state()
    assert upgrade is not None, "approval_denied has no safe alternative; must upgrade on first block"


def test_unknown_tool_is_not_immediate_upgrade(tmp_path):
    agent = build_agent(tmp_path, [])
    _record_denial(agent, "unknown_tool", "write_file", {"path": "x.txt"})
    assert agent.evaluate_blocked_state() is None, "unknown_tool is a fixable mistake; give an alternative chance"


def test_upgrade_contains_attempts_and_root_cause(tmp_path):
    agent = build_agent(tmp_path, [])
    _record_denial(agent, "tool_not_allowed", "write_file", {"path": "x.txt"})
    _record_denial(agent, "tool_not_allowed", "patch_file", {"path": "x.txt"})
    _record_denial(agent, "tool_not_allowed", "write_file", {"path": "x.txt"})
    upgrade = agent.evaluate_blocked_state()
    assert upgrade is not None
    assert upgrade["attempts"]  # what the agent tried
    assert upgrade["root_cause"]
    assert upgrade["question"]


def test_no_duplicate_upgrade_for_same_root(tmp_path):
    agent = build_agent(tmp_path, [])
    _record_denial(agent, "tool_not_allowed", "write_file", {"path": "x.txt"})
    _record_denial(agent, "tool_not_allowed", "write_file", {"path": "x.txt"})
    first = agent.evaluate_blocked_state()
    assert first is not None
    # Same root again in the same run must not re-upgrade.
    _record_denial(agent, "tool_not_allowed", "write_file", {"path": "x.txt"})
    assert agent.evaluate_blocked_state() is None


def test_upgrade_calls_ask_user_callback_when_present(tmp_path):
    agent = build_agent(tmp_path, [], ask_user_callback=lambda question, choices: "use read-only")
    _record_denial(agent, "tool_not_allowed", "write_file", {"path": "x.txt"})
    _record_denial(agent, "tool_not_allowed", "write_file", {"path": "x.txt"})

    agent.upgrade_to_user("blocked", "what to do?")
    # The callback must have been invoked deterministically (not left to the model).
    assert agent.last_ask_user_answer == "use read-only"


def test_upgrade_without_callback_emits_event_not_block(tmp_path):
    agent = build_agent(tmp_path, [])
    _record_denial(agent, "tool_not_allowed", "write_file", {"path": "x.txt"})
    _record_denial(agent, "tool_not_allowed", "write_file", {"path": "x.txt"})

    events = []
    original_emit = agent.session_event_bus.emit

    def capture_emit(event, payload=None):
        events.append(event)
        return original_emit(event, payload)

    agent.session_event_bus.emit = capture_emit
    agent.upgrade_to_user("blocked", "what to do?")
    assert "blocked_upgrade" in events, "without a callback the upgrade must be surfaced as an event, not block"


def test_engine_tool_failure_triggers_upgrade_end_to_end(tmp_path):
    # Integration: a real ask() where write_file is denied (approval_denied,
    # irreplaceable) must drive the engine hook into upgrade_to_user.
    answers = []
    agent = build_agent(
        tmp_path,
        [
            '<tool>{"name":"write_file","args":{"path":"secret.txt","content":"x"}}</tool>',
            '<tool>{"name":"write_file","args":{"path":"secret2.txt","content":"y"}}</tool>',
            "<final>Stopped.</final>",
        ],
        approval_policy="never",
        ask_user_callback=lambda question, choices: answers.append(question) or "user choice",
    )
    agent.ask("write these files")

    assert answers, "the engine hook must have escalated to the user callback"
    assert any("Blocked" in q or "blocked" in q for q in answers)
