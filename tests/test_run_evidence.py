from pathlib import Path

from repo_harness.release_evidence import SCENARIO_IDS, run_phase2_scenario_gate


def test_phase2_release_evidence_runner_writes_repo_harness_artifacts(tmp_path):
    output_dir = tmp_path / "release" / "v3-compat-phase2"

    result = run_phase2_scenario_gate(output_dir)

    assert result["status"] == "passed"
    assert result["scenario_count"] == len(SCENARIO_IDS)
    assert {row["id"] for row in result["rows"]} == set(SCENARIO_IDS)
    assert all(row["status"] == "passed" for row in result["rows"])
    assert (output_dir / "phase2-evidence.json").exists()
    assert (output_dir / "TESTING.md").exists()
    text = (output_dir / "TESTING.md").read_text(encoding="utf-8")
    assert "RepoHarness v3-Compat Phase 2" in text
    removed_state_dir = "." + "pi" + "co"
    assert removed_state_dir not in text
    assert not Path("release/v3").exists()
    assert Path(result["runtime_report"]).is_file()
    assert Path(result["runtime_trace"]).is_file()
    assert Path(result["session_events"]).is_file()
    dogfood_row = next(row for row in result["rows"] if row["id"] == "business-dogfood-fake-provider")
    assert "order_pricing_bugfix" in dogfood_row["detail"]
    assert "release_readiness_review" in dogfood_row["detail"]
    assert "incident_resume_fix" in dogfood_row["detail"]
