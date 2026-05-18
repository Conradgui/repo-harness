from pathlib import Path


def test_core_modules_are_real_boundaries_not_shims():
    root = Path(__file__).resolve().parents[1]
    minimum_lines = {
        "repo_harness/core/tool_executor.py": 120,
        "repo_harness/core/permissions.py": 55,
        "repo_harness/core/tool_policy.py": 55,
        "repo_harness/core/compact.py": 60,
        "repo_harness/core/context_usage.py": 40,
        "repo_harness/core/worker_manager.py": 120,
        "repo_harness/features/skills.py": 120,
        "repo_harness/features/skills_runtime.py": 70,
        "repo_harness/tui/widgets.py": 160,
        "repo_harness/evaluation/run_evidence.py": 100,
    }
    for relative, minimum in minimum_lines.items():
        lines = (root / relative).read_text(encoding="utf-8").splitlines()
        assert len(lines) >= minimum, f"{relative} still looks like a shim"

