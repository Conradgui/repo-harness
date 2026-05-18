import json

from repo_harness.evaluation.run_evidence import RunEvidence


def test_run_evidence_drives_public_cli_and_records_logs(tmp_path):
    evidence = RunEvidence(tmp_path / "evidence")

    result = evidence.run_public_cli_smoke()

    assert result["status"] == "passed"
    assert result["driver"] == "public_cli"
    assert result["exit_code"] == 0
    assert "RepoHarness" in result["stdout"]
    assert "Commands:" in result["stdout"]
    assert (tmp_path / "evidence" / "logs" / "public-cli-smoke.stdout.txt").exists()


def test_run_evidence_run_writes_structured_payload(tmp_path):
    payload = RunEvidence(tmp_path / "evidence").run()

    assert payload["status"] == "passed"
    assert payload["schema_version"] == "repo-harness-run-evidence-v1"
    assert {row["id"] for row in payload["scenarios"]} >= {"public_cli_smoke", "scripted_runtime_smoke"}
    assert (tmp_path / "evidence" / "run-evidence.json").exists()
    stored = json.loads((tmp_path / "evidence" / "run-evidence.json").read_text(encoding="utf-8"))
    assert stored["status"] == payload["status"]
