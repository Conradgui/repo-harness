"""Session, task and run identifiers are stamped in UTC.

These identifiers are sorted and compared across machines, and they sit next to
`created_at`, which has always been UTC. Stamping them in local time made the
two disagree and made ordering unreliable: a DST fall-back repeats an hour, so
two runs an hour apart can produce identifiers that sort backwards.
"""

import re
from datetime import datetime, timedelta, timezone

from conftest import build_agent

from repo_harness.task_state import TaskState
from repo_harness.workspace import id_timestamp

STAMP = re.compile(r"(\d{8}-\d{6})")


def _stamp_of(identifier):
    match = STAMP.search(identifier)
    assert match, f"no timestamp found in {identifier!r}"
    return datetime.strptime(match.group(1), "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)


def _assert_is_utc_now(identifier):
    delta = abs(_stamp_of(identifier) - datetime.now(timezone.utc))
    assert delta < timedelta(minutes=5), (
        f"{identifier!r} is {delta} away from UTC now -- it is probably local time"
    )


def test_id_timestamp_is_utc():
    _assert_is_utc_now(id_timestamp())


def test_session_id_is_stamped_in_utc(tmp_path):
    agent = build_agent(tmp_path, [])

    _assert_is_utc_now(agent.session["id"])


def test_session_id_and_created_at_agree(tmp_path):
    agent = build_agent(tmp_path, [])

    created_at = datetime.fromisoformat(agent.session["created_at"])
    drift = abs(_stamp_of(agent.session["id"]) - created_at)

    # Both are written in the same breath; a gap of minutes means one of them
    # is on a different clock.
    assert drift < timedelta(minutes=5), f"id and created_at disagree by {drift}"


def test_task_and_run_ids_are_stamped_in_utc(tmp_path):
    agent = build_agent(tmp_path, [])

    _assert_is_utc_now(agent.new_task_id())
    _assert_is_utc_now(agent.new_run_id())


def test_task_state_run_id_is_stamped_in_utc():
    _assert_is_utc_now(TaskState.create("task_1", "demo").run_id)


def test_identifiers_keep_their_prefixes():
    assert TaskState.create("task_1", "demo").run_id.startswith("run_")
