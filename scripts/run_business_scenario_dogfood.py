"""Run the RepoHarness business dogfood scenario pack."""

import argparse
import json
import os
from pathlib import Path
from types import SimpleNamespace

from repo_harness.config import resolve_runtime_config
from repo_harness.models import AnthropicCompatibleModelClient, FakeModelClient, OpenAICompatibleModelClient
from repo_harness.runtime import RepoHarness
from repo_harness.session_store import SessionStore
from repo_harness.workspace import WorkspaceContext, now


SCENARIOS = (
    {
        "id": "order_pricing_bugfix",
        "prompt": "Fix the order pricing calculation and summarize the change.",
        "files": {"src/pricing.py": "def total(items):\n    return sum(item['price'] for item in items)\n"},
        "fake_outputs": [
            '<tool>{"name":"patch_file","args":{"path":"src/pricing.py","old_text":"return sum(item[\'price\'] for item in items)","new_text":"return sum(item[\'price\'] * item.get(\'qty\', 1) for item in items)"}}</tool>',
            "<final>pricing bug fixed</final>",
        ],
        "expected": "pricing bug fixed",
    },
    {
        "id": "release_readiness_review",
        "prompt": "Review release readiness and write the internal checklist.",
        "files": {"RELEASE.md": "# Release\n\n- tests pending\n"},
        "fake_outputs": [
            '<tool>{"name":"write_file","args":{"path":".repo-harness/review/release-readiness.md","content":"# Release Readiness\\n- Tests pending\\n- Review queue checked\\n"}}</tool>',
            "<final>release review drafted</final>",
        ],
        "expected": "release review drafted",
    },
    {
        "id": "incident_resume_fix",
        "prompt": "Resume the incident task and capture the next action.",
        "files": {"INCIDENT.md": "# Incident\n\nNeed resume note.\n"},
        "fake_outputs": [
            '<tool>{"name":"write_file","args":{"path":".repo-harness/review/incident-resume.md","content":"# Incident Resume\\nNext action: verify recovery path.\\n"}}</tool>',
            "<final>incident resume captured</final>",
        ],
        "expected": "incident resume captured",
    },
)


def run_dogfood(output_dir, live=None):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    live = _live_enabled() if live is None else bool(live)
    scenarios = [_run_scenario(output_dir, scenario, live=live) for scenario in SCENARIOS]
    status = "passed" if all(item["status"] == "passed" for item in scenarios) else "failed"
    payload = {
        "schema_version": "repo-harness-business-dogfood-v1",
        "status": status,
        "provider_mode": "live" if live else "fake",
        "scenarios": scenarios,
        "generated_at": now(),
        "output_dir": str(output_dir),
    }
    (output_dir / "business-dogfood.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def _run_scenario(output_dir, scenario, live=False):
    workspace = output_dir / "workspaces" / scenario["id"]
    workspace.mkdir(parents=True, exist_ok=True)
    for relative, content in scenario["files"].items():
        path = workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    agent = _build_agent(workspace, scenario, live=live)
    try:
        answer = agent.ask(scenario["prompt"])
        passed = bool(answer) if live else answer == scenario["expected"]
        detail = answer
    except Exception as exc:
        passed = False
        detail = str(exc)
    artifacts = {
        "workspace": str(workspace),
        "state_dir": str(workspace / ".repo-harness"),
    }
    current_run_dir = getattr(agent, "current_run_dir", None)
    if current_run_dir:
        artifacts.update(
            {
                "run_dir": str(current_run_dir),
                "report": str(Path(current_run_dir) / "report.json"),
                "trace": str(Path(current_run_dir) / "trace.jsonl"),
            }
        )
    return {
        "id": scenario["id"],
        "status": "passed" if passed else "failed",
        "provider_mode": "live" if live else "fake",
        "detail": detail,
        "artifacts": artifacts,
        "checked_at": now(),
    }


def _build_agent(workspace, scenario, live=False):
    workspace_context = WorkspaceContext.build(workspace)
    model_client = _live_model_client(workspace_context) if live else FakeModelClient(scenario["fake_outputs"])
    return RepoHarness(
        model_client=model_client,
        workspace=workspace_context,
        session_store=SessionStore(workspace / ".repo-harness" / "sessions"),
        approval_policy="auto",
    )


def _live_model_client(workspace_context):
    args = SimpleNamespace(
        cwd=str(workspace_context.cwd),
        config=None,
        provider="openai",
        model=None,
        base_url=None,
        max_steps=None,
        max_new_tokens=None,
        sandbox=None,
        sandbox_backend=None,
        _provider_explicit=False,
        _model_explicit=False,
        _base_url_explicit=False,
        _max_steps_explicit=False,
        _max_new_tokens_explicit=False,
    )
    config = resolve_runtime_config(args, workspace_context)
    profile = config.provider_profile
    api_key = os.environ.get(profile.api_key_env, "")
    if profile.client == "anthropic":
        return AnthropicCompatibleModelClient(
            model=profile.model,
            base_url=profile.base_url,
            api_key=api_key,
            temperature=0.2,
            timeout=300,
        )
    return OpenAICompatibleModelClient(
        model=profile.model,
        base_url=profile.base_url,
        api_key=api_key,
        temperature=0.2,
        timeout=300,
    )


def _live_enabled():
    return os.environ.get("REPO_HARNESS_RUN_LIVE_BUSINESS_DOGFOOD") == "1"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="release/business-dogfood",
        help="RepoHarness dogfood evidence output directory.",
    )
    parser.add_argument("--live", action="store_true", help="Use configured live provider instead of scripted fake output.")
    args = parser.parse_args(argv)
    payload = run_dogfood(Path(args.output), live=args.live or None)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
