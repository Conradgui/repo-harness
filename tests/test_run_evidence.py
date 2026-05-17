from pathlib import Path

from repo_harness.release_evidence import run_phase2_scenario_gate


def test_phase2_release_evidence_runner_writes_repo_harness_artifacts(tmp_path):
    output_dir = tmp_path / "release" / "v3-compat-phase2"

    result = run_phase2_scenario_gate(output_dir)

    assert result["status"] == "passed"
    assert result["scenario_count"] >= 6
    assert (output_dir / "phase2-evidence.json").exists()
    assert (output_dir / "TESTING.md").exists()
    text = (output_dir / "TESTING.md").read_text(encoding="utf-8")
    assert "RepoHarness v3-Compat Phase 2" in text
    removed_state_dir = "." + "pi" + "co"
    assert removed_state_dir not in text
    assert not Path("release/v3").exists()
