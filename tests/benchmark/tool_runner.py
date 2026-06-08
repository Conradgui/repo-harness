"""Tool Runner — 使用 RepoHarness 完整流程执行任务。"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import get_deepseek_client, setup_rich_workspace

from repo_harness import RepoHarness, SessionStore, WorkspaceContext


def run_tool_task(task, tmp_path, client_factory=None):
    """用 RepoHarness 执行任务。

    Args:
        task: 任务字典
        tmp_path: 临时目录路径

    Returns:
        (agent, elapsed_seconds, response_text, error_text)
    """
    # 设置工作区
    setup_rich_workspace(tmp_path, files_to_copy=[
        "rich/markdown.py",
        "rich/__init__.py",
        "tests/test_markdown.py",
        "tests/__init__.py",
        "README.md",
    ])

    client = client_factory() if client_factory is not None else get_deepseek_client(timeout=60)
    if client is None:
        return None, 0, "", "no client"

    workspace = WorkspaceContext.build(tmp_path)
    store = SessionStore(str(tmp_path / ".repo-harness" / "sessions"))
    agent = RepoHarness(
        model_client=client,
        workspace=workspace,
        session_store=store,
        approval_policy="auto",
        max_steps=15,
        max_new_tokens=2048,
    )

    start = time.time()
    response_text = ""
    error_text = ""
    try:
        response_text = agent.ask(task["prompt"])
        agent._last_response = response_text
    except Exception as e:
        error_text = f"{type(e).__name__}: {e}"
    elapsed = time.time() - start

    return agent, elapsed, response_text, error_text
