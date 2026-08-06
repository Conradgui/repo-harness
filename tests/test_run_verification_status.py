"""G1: run status and result verification must be independent contracts.

The product contract (RepoHarness 产品缺口交接, G1) says "the control loop
finished" and "the result was verified" are two different facts. A `<final>`
answer ends the control loop (run_status=completed) but does NOT verify the
user's goal (verification_status stays not_run unless evidence shows a
verification actually ran and passed). Only completed ∧ passed is a verified
outcome.

The activation path is Auto Issue Fix: it already has infer_test_commands +
run_test_commands (auto_issue_fix/workspace.py), and after running them it
writes the results into verification_evidence and marks the status. The
general runtime stays not_run after a final answer -- honest, never pretending
to be verified.
"""

import json

from repo_harness import FakeModelClient, RepoHarness, SessionStore, WorkspaceContext
from repo_harness.auto_issue_fix.workspace import infer_test_commands, run_test_commands


def build_agent(tmp_path, outputs, **kwargs):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    return RepoHarness(
        model_client=FakeModelClient(outputs),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".repo-harness" / "sessions"),
        approval_policy="auto",
        **kwargs,
    )


def _read_report(agent):
    return json.loads((agent.current_run_dir / "report.json").read_text(encoding="utf-8"))


def _read_task_state(agent):
    return json.loads((agent.current_run_dir / "task_state.json").read_text(encoding="utf-8"))


def test_final_does_not_mark_verification_passed(tmp_path):
    agent = build_agent(tmp_path, ["<final>Done.</final>"])
    agent.ask("explain the repo")

    task_state = _read_task_state(agent)
    report = _read_report(agent)
    # The control loop ended normally...
    assert task_state["status"] == "completed"
    assert task_state["stop_reason"] == "final_answer_returned"
    # ...but that is NOT a claim that verification passed.
    assert task_state["verification_status"] == "not_run"
    assert report["verification_status"] == "not_run"


def test_verification_status_not_run_for_explanation_task(tmp_path):
    # A task with no verification plan (no tests, no build) must stay not_run,
    # not pretend to be passed.
    agent = build_agent(tmp_path, ["<final>This is an investigation.</final>"])
    agent.ask("investigate the layout")

    report = _read_report(agent)
    assert report["verification_status"] == "not_run"


def test_completed_not_run_has_no_verified_wording(tmp_path):
    # Decision table row 2: completed ∧ not_run must not claim "verified" or
    # "tests passed" anywhere in the report.
    agent = build_agent(tmp_path, ["<final>Here is the answer.</final>"])
    agent.ask("explain")

    report = _read_report(agent)
    assert report["verification_status"] == "not_run"
    payload = json.dumps(report, ensure_ascii=False).lower()
    assert "verified" not in payload
    assert "tests passed" not in payload


def test_mark_verification_passed_records_evidence(tmp_path):
    agent = build_agent(tmp_path, ["<final>Done.</final>"])
    agent.ask("fix the bug")

    agent.current_task_state.mark_verification(
        "passed",
        [{"command": "uv run python -m pytest -q", "returncode": 0, "status": "passed", "output_summary": "tests passed"}],
    )
    agent.run_store.write_task_state(agent.current_task_state)

    task_state = _read_task_state(agent)
    assert task_state["verification_status"] == "passed"
    assert task_state["verification_evidence"]
    assert task_state["verification_evidence"][0]["status"] == "passed"


def test_verification_failed_does_not_claim_verified(tmp_path):
    agent = build_agent(tmp_path, ["<final>Done.</final>"])
    agent.ask("fix the bug")

    agent.current_task_state.mark_verification(
        "failed",
        [{"command": "uv run python -m pytest -q", "returncode": 1, "status": "failed", "output_summary": "1 failed"}],
    )
    agent.run_store.write_task_state(agent.current_task_state)
    # Regenerate the report so it reflects the verification result.
    agent.run_store.write_report(agent.current_task_state, agent.redact_artifact(agent.build_report(agent.current_task_state)))

    report = _read_report(agent)
    assert report["verification_status"] == "failed"
    assert "verified" not in json.dumps(report, ensure_ascii=False).lower()


def test_old_task_state_dict_migrates_to_not_run(tmp_path):
    agent = build_agent(tmp_path, ["<final>Done.</final>"])
    agent.ask("task")

    from repo_harness.task_state import TaskState

    old = agent.current_task_state.to_dict()
    old.pop("verification_status", None)
    old.pop("verification_evidence", None)

    restored = TaskState.from_dict(old)
    assert restored.verification_status == "not_run"
    assert restored.verification_evidence == []


def test_partial_verification(tmp_path):
    agent = build_agent(tmp_path, ["<final>Done.</final>"])
    agent.ask("task")

    agent.current_task_state.mark_verification(
        "partial",
        [
            {"command": "npm test", "returncode": 0, "status": "passed", "output_summary": "ok"},
            {"command": "npm run build", "returncode": 1, "status": "failed", "output_summary": "build failed"},
        ],
    )
    agent.run_store.write_task_state(agent.current_task_state)

    task_state = _read_task_state(agent)
    assert task_state["verification_status"] == "partial"


def test_auto_issue_fix_test_results_write_verification_evidence(tmp_path):
    # The activation path: Auto Issue Fix runs its existing test stack, then
    # the results flow into the runtime's verification_evidence.
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()

    script = tmp_path / "run_tests.py"
    script.write_text("print('ok')\n", encoding="utf-8")

    commands = infer_test_commands(tmp_path)
    assert commands, "pyproject + tests dir must infer a pytest command"

    # Simulate the Auto Issue Fix runner executing its inferred commands and
    # then writing evidence into the task state (as run_live_auto_issue_fix
    # will after the fix turn).
    results = run_test_commands(commands, tmp_path, tmp_path / "test-after-fix.log")
    agent = build_agent(tmp_path, ["<final>Fixed.</final>"])
    agent.ask("fix the tests")

    all_passed = all(r["status"] == "passed" for r in results)
    agent.current_task_state.mark_verification(
        "passed" if all_passed else "failed",
        [{"command": r["command"], "returncode": r["returncode"], "status": r["status"], "output_summary": ""} for r in results],
    )
    agent.run_store.write_task_state(agent.current_task_state)

    task_state = _read_task_state(agent)
    assert task_state["verification_evidence"], "verification evidence must be recorded"
    assert task_state["verification_status"] in {"passed", "failed"}
    # The evidence reflects the actual run: every command's status is captured.
    assert all("status" in e for e in task_state["verification_evidence"])


def test_not_run_tests_are_not_counted_as_passed(tmp_path):
    # A dry-run or skipped command (status="not_run") must never count as
    # verification passed -- honest exposure over pretending.
    from repo_harness.auto_issue_fix.config import AutoIssueFixRunRecord

    record = AutoIssueFixRunRecord(
        run_id="r1",
        mode="draft-auto",
        repo="example/project",
        issue=1,
        workspace_path=str(tmp_path),
        evidence_dir=str(tmp_path / "evidence"),
        status="completed",
        summary="dry run",
        tests=[{"command": "python -m pytest -q", "status": "not_run", "returncode": None}],
    )
    assert record.verification_status == "not_run"
    # A mix where nothing actually ran is still not_run, not partial or passed.
    record2 = AutoIssueFixRunRecord(
        run_id="r2",
        mode="draft-auto",
        repo="example/project",
        issue=1,
        workspace_path=str(tmp_path),
        evidence_dir=str(tmp_path / "evidence"),
        status="completed",
        summary="dry run",
        tests=[
            {"command": "npm test", "status": "not_run", "returncode": None},
            {"command": "npm run build", "status": "not_run", "returncode": None},
        ],
    )
    assert record2.verification_status == "not_run"


def test_run_record_json_exposes_verification_status(tmp_path):
    from repo_harness.auto_issue_fix.config import AutoIssueFixRunRecord
    from repo_harness.auto_issue_fix.evidence import _public_record

    record = AutoIssueFixRunRecord(
        run_id="r3",
        mode="review-gated",
        repo="example/project",
        issue=2,
        workspace_path=str(tmp_path),
        evidence_dir=str(tmp_path / "evidence"),
        status="completed",
        summary="verified",
        tests=[
            {"command": "python -m pytest -q", "status": "passed", "returncode": 0},
            {"command": "npm test", "status": "passed", "returncode": 0},
        ],
    )
    public = _public_record(record, include_local_paths=False)
    assert public["verification_status"] == "passed"
    assert len(public["verification_evidence"]) == 2
    assert public["verification_evidence"][0]["status"] == "passed"
