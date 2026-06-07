"""Baseline LLM Runner — 直接调裸模型 API，不使用任何工具。"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import get_deepseek_client


def run_baseline(task, client_factory=None):
    """用裸模型 API 执行任务，返回响应文本。

    Args:
        task: 任务字典，包含 baseline_prompt 字段

    Returns:
        (response_text, elapsed_seconds)
    """
    client = client_factory() if client_factory is not None else get_deepseek_client(timeout=60)
    if client is None:
        return "[ERROR] No DeepSeek API key available", 0

    prompt = task["baseline_prompt"]
    start = time.time()
    try:
        result = client.complete(prompt, 2048)
        elapsed = time.time() - start
        return result, elapsed
    except Exception as e:
        elapsed = time.time() - start
        return f"[ERROR] {type(e).__name__}: {e}", elapsed
