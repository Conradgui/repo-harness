import importlib.util
import inspect
import os
from pathlib import Path

import pytest


def _load_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "run_business_scenario_dogfood.py"
    spec = importlib.util.spec_from_file_location("run_business_scenario_dogfood", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_business_scenario_dogfood_uses_provider_config_not_release_gate_only():
    dogfood = _load_module()
    source = inspect.getsource(dogfood)

    assert "run_phase2_scenario_gate" not in source
    assert "resolve_runtime_config" in source
    assert "OpenAICompatibleModelClient" in source
    assert "AnthropicCompatibleModelClient" in source
    assert hasattr(dogfood, "run_dogfood")


@pytest.mark.skipif(
    os.environ.get("REPO_HARNESS_RUN_LIVE_BUSINESS_DOGFOOD") != "1",
    reason="live provider dogfood is opt-in",
)
def test_business_scenario_dogfood_live_provider_opt_in(tmp_path):
    dogfood = _load_module()
    summary = dogfood.run_dogfood(tmp_path / "business-dogfood")

    assert summary["status"] == "passed"
    assert {scenario["id"] for scenario in summary["scenarios"]} == {
        "order_pricing_bugfix",
        "release_readiness_review",
        "incident_resume_fix",
    }
