"""Shared helpers for the benchmark harness."""

import os
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RICH_REPO = PROJECT_ROOT / "test_repos" / "rich"


def load_authorized_env(names=("DEEPSEEK_API_KEY", "MIMO_API_KEY")):
    """Load API keys from user/machine env scopes when PowerShell did not inherit them."""
    if sys.platform != "win32":
        return
    try:
        for name in names:
            if os.environ.get(name):
                continue
            script = (
                f"$v=[Environment]::GetEnvironmentVariable('{name}','User'); "
                f"if (-not $v) {{ $v=[Environment]::GetEnvironmentVariable('{name}','Machine') }}; "
                "$v"
            )
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            value = (completed.stdout or "").strip()
            if value:
                os.environ[name] = value
    except Exception:
        pass


def get_mimo_client(timeout=60):
    """Create a MIMO model client when MIMO_API_KEY is available."""
    load_authorized_env(("MIMO_API_KEY",))
    key = os.environ.get("MIMO_API_KEY")
    if not key:
        return None
    from repo_harness.models import ChatCompletionsCompatibleModelClient

    return ChatCompletionsCompatibleModelClient(
        model="mimo-v2.5-pro",
        base_url="https://token-plan-cn.xiaomimimo.com/v1",
        api_key=key,
        temperature=0.2,
        timeout=timeout,
    )


def get_deepseek_client(timeout=60):
    """Create a DeepSeek model client when DEEPSEEK_API_KEY is available."""
    load_authorized_env(("DEEPSEEK_API_KEY",))
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        return None
    from repo_harness.models import ChatCompletionsCompatibleModelClient

    return ChatCompletionsCompatibleModelClient(
        model="deepseek-v4-pro",
        base_url="https://api.deepseek.com",
        api_key=key,
        temperature=0.2,
        timeout=timeout,
    )


def setup_rich_workspace(tmp_path, files_to_copy=None):
    """Copy a local Rich fixture into a temporary benchmark workspace."""
    rich_repo = Path(os.environ.get("REPO_HARNESS_BENCHMARK_REPO", DEFAULT_RICH_REPO)).resolve()
    if not rich_repo.exists():
        raise FileNotFoundError(
            "benchmark fixture not found. Set REPO_HARNESS_BENCHMARK_REPO "
            "to a local checkout of Textualize/rich before running the benchmark."
        )
    if files_to_copy is None:
        candidates = [p.relative_to(rich_repo) for p in rich_repo.rglob("*") if p.is_file()]
    else:
        candidates = [Path(p) for p in files_to_copy]
    for rel_path in candidates:
        source = rich_repo / rel_path
        if not source.is_file():
            continue
        dest = tmp_path / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
