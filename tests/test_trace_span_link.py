"""Trace events form a parent chain inside a run, and child runs carry the
parent's run/span ids.

The audit trail should answer "what did this agent do, and which child runs did
it spawn". Within a run, each event's span_id links to the previous event
(parent_span_id), so the sequence is a chain. A child run stamps its inherited
parent_run_id/parent_span_id on its events, joining the two traces.

These are behaviour tests: they assert the links exist and are consistent, not
the exact span string format.
"""

import json

from repo_harness import FakeModelClient, RepoHarness, SessionStore, WorkspaceContext


def build_agent(tmp_path, outputs, **kwargs):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    return RepoHarness(
        model_client=FakeModelClient(outputs),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".repo-harness" / "sessions"),
        approval_policy="auto",
        **kwargs,
    )


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_run_events_form_a_parent_chain(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            '<tool>{"name":"read_file","args":{"path":"README.md"}}</tool>',
            "<final>Done.</final>",
        ],
    )
    agent.ask("inspect README.md")

    events = read_jsonl(agent.current_run_dir / "trace.jsonl")
    # current_run_id is cleared after ask(); task_state keeps the real run id.
    run_id = agent.current_task_state.run_id
    events = [e for e in events if e.get("run_id") == run_id]

    assert len(events) >= 3, "expected run_started + tool + final events"
    # First event has no parent span (chain start).
    assert events[0].get("parent_span_id", "") == ""
    assert events[0].get("span_id")

    # Each subsequent event names the previous event's span as its parent.
    # events[1:] is intentionally one shorter than events (strict=False).
    for prev, cur in zip(events, events[1:], strict=False):
        assert cur["span_id"], "span_id must be set"
        assert cur["span_id"] != prev["span_id"], "span ids must be distinct"
        assert cur["parent_span_id"] == prev["span_id"], (
            f"event {cur['event']} parent_span_id {cur.get('parent_span_id')!r} "
            f"!= previous span {prev['span_id']!r}; chain is broken"
        )


def test_child_inherits_parent_run_and_span_ids(tmp_path):
    parent = build_agent(
        tmp_path,
        [
            '<tool>{"name":"read_file","args":{"path":"README.md"}}</tool>',
            "<final>Done.</final>",
        ],
    )
    parent.ask("inspect README.md")
    parent_run_id = parent.current_task_state.run_id
    parent_span = None
    parent_events = read_jsonl(parent.current_run_dir / "trace.jsonl")
    for event in parent_events:
        if event.get("run_id") == parent_run_id:
            parent_span = event["span_id"]

    # A child constructed with the parent's ids, as build_child_runtime /
    # tool_delegate do, stamps them on every trace event.
    child = build_agent(
        tmp_path,
        ["<final>Child done.</final>"],
        parent_run_id=parent_run_id,
        parent_span_id=parent_span,
    )
    child.ask("child task")

    child_run_id = child.current_task_state.run_id
    child_events = read_jsonl(child.current_run_dir / "trace.jsonl")
    child_events = [e for e in child_events if e.get("run_id") == child_run_id]
    assert child_events, "child run produced no trace events"
    # run_started is the first event and must carry the inherited parent ids.
    started = child_events[0]
    assert started["parent_run_id"] == parent_run_id
    assert started["inherited_parent_span_id"] == parent_span
