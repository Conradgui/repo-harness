from repo_harness.auto_issue_fix import GhCliBackend, run_live_auto_issue_fix


def test_auto_issue_fix_live_runner_public_entrypoints_are_importable():
    assert GhCliBackend is not None
    assert run_live_auto_issue_fix is not None
