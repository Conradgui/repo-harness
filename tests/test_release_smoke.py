from pathlib import Path

from repo_harness.evaluation import run_evidence


def test_run_evidence_smoke_uses_repo_harness_branding(tmp_path):
    payload = run_evidence.run(tmp_path / "release-smoke")
    text = (tmp_path / "release-smoke" / "run-evidence.json").read_text(encoding="utf-8")

    assert payload["status"] == "passed"
    assert "RepoHarness" in text
    assert ".repo-harness" in text
    removed_state_dir = "." + "pi" + "co"
    assert removed_state_dir not in text
    assert not Path("release/v3").exists()
