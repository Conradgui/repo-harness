import json
import os
import subprocess
import sys

from repo_harness.auto_pr import (
    AutoPrConfig,
    AutoPrReviewGate,
    AutoPrRunRecord,
    handle_auto_pr_repl_command,
    render_evidence_templates,
    review_gates_block_reason,
    run_auto_pr,
    redact_text,
    write_evidence,
)


def test_auto_pr_templates_are_portable_and_redacted_by_default(tmp_path):
    local_workspace = tmp_path / "workspace"
    local_workspace.mkdir()
    record = AutoPrRunRecord(
        run_id="auto_pr_20260525_000000",
        mode="review-gated",
        repo="https://github.com/example/project",
        issue=123,
        workspace_path=str(local_workspace),
        evidence_dir=str(local_workspace / ".repo-harness" / "auto-pr" / "auto_pr_20260525_000000"),
        status="planned",
        summary="Token sk-secret-123 and ghp_secret_456 must not leak.",
        tests=[{"command": "python -m pytest -q", "status": "not_run"}],
    )

    rendered = render_evidence_templates(record, include_local_paths=False)

    assert set(rendered) == {"run-record.md", "pr-body.md", "formal-report-summary.md", "run-record.json"}
    combined = "\n".join(rendered.values())
    assert str(local_workspace) not in combined
    assert "sk-secret-123" not in combined
    assert "ghp_secret_456" not in combined
    assert "<workspace>" in combined
    assert "<evidence_dir>" in combined
    assert "<redacted>" in combined

    payload = json.loads(rendered["run-record.json"])
    assert payload["workspace_path"] == "<workspace>"
    assert payload["evidence_dir"] == "<evidence_dir>"


def test_auto_pr_redaction_covers_common_secret_shapes():
    text = "OPENAI_API_KEY=sk-test123 GITHUB_TOKEN=gho_abc123 cookie=sessionid"

    redacted = redact_text(text)

    assert "sk-test123" not in redacted
    assert "gho_abc123" not in redacted
    assert "sessionid" not in redacted
    assert redacted.count("<redacted>") >= 3


def test_auto_pr_cli_dry_run_writes_standard_evidence_files(tmp_path):
    evidence_dir = tmp_path / "evidence"
    env = dict(os.environ)
    env["PYTHONPATH"] = os.getcwd() + os.pathsep + env.get("PYTHONPATH", "")
    command = [
        sys.executable,
        "-m",
        "repo_harness",
        "auto-pr",
        "--repo",
        "https://github.com/example/project",
        "--issue",
        "123",
        "--evidence-dir",
        str(evidence_dir),
        "--dry-run",
    ]

    completed = subprocess.run(command, cwd=os.getcwd(), env=env, text=True, capture_output=True, timeout=30, check=False)

    assert completed.returncode == 0, completed.stderr
    assert "Auto PR safe preview complete" in completed.stdout
    for name in ("run-record.md", "pr-body.md", "formal-report-summary.md", "run-record.json"):
        assert (evidence_dir / name).is_file()
    for name in (
        "reviews/review-task.json",
        "reviews/review-plan.json",
        "reviews/review-context.json",
        "reviews/review-diff.json",
        "reviews/review-tests.json",
        "reviews/review-security.json",
        "reviews/review-pr-readiness.json",
        "decision-log.jsonl",
        "checkpoint.json",
    ):
        assert (evidence_dir / name).is_file()


def test_auto_pr_draft_auto_requires_explicit_risk_acknowledgement(tmp_path):
    config = AutoPrConfig(
        repo="https://github.com/example/project",
        issue=123,
        mode="draft-auto",
        evidence_dir=tmp_path,
        dry_run=True,
    )

    assert "automatic review gates" in config.risk_notice()
    assert "block verdict" in config.risk_notice()


def test_auto_pr_review_gated_also_records_auto_review_gates(tmp_path):
    config = AutoPrConfig(
        repo="https://github.com/example/project",
        issue=123,
        mode="review-gated",
        evidence_dir=tmp_path,
        dry_run=True,
    )

    record = run_auto_pr(config)

    assert record.auto_review == "required"
    assert [gate.stage for gate in record.review_gates] == [
        "task",
        "plan",
        "context",
        "diff",
        "tests",
        "security",
        "pr-readiness",
    ]
    assert {gate.verdict for gate in record.review_gates} == {"pass"}


def test_auto_pr_draft_auto_cannot_disable_auto_review():
    config = AutoPrConfig(
        repo="https://github.com/example/project",
        issue=123,
        mode="draft-auto",
        dry_run=True,
        auto_review="off",
    )

    try:
        config.validate()
    except ValueError as exc:
        assert "auto-review must be required" in str(exc)
    else:
        raise AssertionError("draft-auto must reject disabled automatic review gates")


def test_auto_pr_rejects_negative_review_repair_limit():
    config = AutoPrConfig(
        repo="https://github.com/example/project",
        issue=123,
        dry_run=True,
        max_review_repairs=-1,
    )

    try:
        config.validate()
    except ValueError as exc:
        assert "max-review-repairs" in str(exc)
    else:
        raise AssertionError("negative max_review_repairs should fail validation")


def test_auto_pr_needs_fix_stops_after_max_review_repairs():
    gate = AutoPrReviewGate(
        stage="diff",
        title="Diff 审查",
        verdict="needs_fix",
        summary="Unrelated file changed.",
        required_action="run bounded repair",
        repair_attempts=2,
    )

    assert review_gates_block_reason((gate,), max_review_repairs=2) == "diff review gate exceeded max review repairs"


def test_auto_pr_failed_gate_generates_fallback_without_pr(tmp_path):
    record = AutoPrRunRecord(
        run_id="auto_pr_failed",
        mode="review-gated",
        repo="https://github.com/example/project",
        issue=123,
        workspace_path=str(tmp_path),
        evidence_dir=str(tmp_path / "evidence"),
        status="failed",
        summary="Tests failed; do not create a PR.",
        tests=[{"command": "python -m pytest -q", "status": "failed"}],
        fallback_reason="test gate failed",
        review_gates=(
            AutoPrReviewGate(
                stage="tests",
                title="测试审查",
                verdict="block",
                summary="test gate failed",
                required_action="stop before PR creation",
            ),
        ),
    )

    rendered = render_evidence_templates(record, include_local_paths=False)

    assert "test gate failed" in rendered["run-record.md"]
    assert "PR creation blocked" in rendered["run-record.md"]
    assert "draft PR" not in rendered["pr-body.md"]
    assert "pr-ready-fallback.md" in rendered


def test_auto_pr_block_verdict_writes_review_artifacts_and_fallback(tmp_path):
    record = AutoPrRunRecord(
        run_id="auto_pr_blocked",
        mode="draft-auto",
        repo="https://github.com/example/project",
        issue=123,
        workspace_path=str(tmp_path),
        evidence_dir=str(tmp_path / "evidence"),
        status="blocked",
        summary="Secret scan failed.",
        tests=[],
        fallback_reason="secret gate failed",
        review_gates=(
            AutoPrReviewGate(
                stage="security",
                title="安全审查",
                verdict="block",
                summary="Secret scan failed.",
                required_action="generate fallback evidence",
            ),
        ),
    )

    write_evidence(record, include_local_paths=False)

    evidence_dir = tmp_path / "evidence"
    assert (evidence_dir / "reviews" / "review-security.json").is_file()
    assert (evidence_dir / "reviews" / "review-security.md").is_file()
    assert (evidence_dir / "decision-log.jsonl").is_file()
    assert (evidence_dir / "checkpoint.json").is_file()
    assert (evidence_dir / "pr-ready-fallback.md").is_file()


def test_auto_pr_repl_defaults_to_discovery_safe_preview(tmp_path):
    code, output = handle_auto_pr_repl_command("", workspace_root=tmp_path)

    assert code == 0
    assert "automatic-discovery safe preview" in output
    assert "Auto PR safe preview complete" in output
    assert list((tmp_path / ".repo-harness" / "auto-pr").glob("auto_pr_*"))
