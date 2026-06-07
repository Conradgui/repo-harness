"""Benchmark 评分器 — 基于规则的自动评分。"""

import json
from pathlib import Path


def evaluate_tool_runner(task, agent, tmp_path, response_text=None):
    """评估 Tool Runner 的输出。"""
    scores = {}
    history = agent.session.get("history", [])
    tool_calls = [h for h in history if h.get("role") == "tool"]

    # 获取最终回答
    final_answer = str(response_text or getattr(agent, "_last_response", "") or "")
    for item in reversed(history):
        if item.get("role") == "assistant":
            final_answer = final_answer or str(item.get("content", ""))
            break

    # 完整性：检查任务是否完成
    scores["completeness"] = _check_completeness(task, agent, tmp_path, final_answer, tool_calls)

    # 可审计性：检查 trace/report/session 是否存在
    scores["auditability"] = _check_audit_trail(agent)

    # 稳定性：检查是否有未处理的异常
    scores["stability"] = _check_stability(agent, history)

    # 可控性：检查是否在边界内
    scores["controllability"] = _check_controllability(agent, tool_calls)

    # 用户体验：检查最终回答是否有帮助
    scores["ux"] = _check_ux(final_answer, task)

    scores["total"] = sum(scores.values())
    scores["response_preview"] = final_answer[:300]
    scores["tool_calls_count"] = len(tool_calls)
    return scores


def evaluate_baseline(task, response_text):
    """评估 Baseline 的输出。"""
    scores = {}

    # 完整性：回答是否包含有用信息
    scores["completeness"] = _check_baseline_completeness(task, response_text)

    # 可审计性：无（只有文本）
    scores["auditability"] = 0

    # 稳定性：回答是否正常
    scores["stability"] = 10 if response_text and len(response_text.strip()) > 50 else (
        5 if response_text and len(response_text.strip()) > 0 else 0
    )

    # 可控性：N/A
    scores["controllability"] = 0

    # 用户体验：回答是否清晰
    scores["ux"] = _check_baseline_ux(response_text)

    scores["total"] = sum(scores.values())
    scores["response_preview"] = (response_text or "")[:300]
    scores["tool_calls_count"] = 0
    return scores


# ── 内部评分函数 ──

def _check_completeness(task, agent, tmp_path, response, tool_calls):
    """完整性评分。"""
    score = 0
    tid = task["id"]

    # 有最终回答
    if response and len(response.strip()) > 20:
        score += 2

    # 有工具调用
    if tool_calls:
        score += 2

    # 回答包含预期关键词
    for kw in task.get("expected_in_response", []):
        if kw.lower() in response.lower():
            score += 1

    # 文件被修改（BM_002, BM_004）
    check_file = task.get("check_file")
    if check_file and task.get("target_line_contains"):
        target = tmp_path / check_file
        if target.exists():
            content = target.read_text(encoding="utf-8")
            if task["target_line_contains"] in content:
                score += 3

    return min(10, score)


def _check_audit_trail(agent):
    """可审计性评分。"""
    score = 0

    # session 文件存在
    if agent.session_path and agent.session_path.exists():
        score += 3

    # run 目录存在
    if agent.current_run_dir and agent.current_run_dir.exists():
        score += 2
        # report.json 存在
        report = agent.current_run_dir / "report.json"
        if report.exists():
            score += 3
        # trace.jsonl 存在
        trace = agent.current_run_dir / "trace.jsonl"
        if trace.exists():
            score += 2

    return min(10, score)


def _check_stability(agent, history):
    """稳定性评分。"""
    score = 10  # 默认满分，扣分制

    # 检查是否有未处理的错误
    for item in history:
        if item.get("role") == "tool":
            content = str(item.get("content", ""))
            if "Traceback" in content or "FATAL" in content:
                score -= 3
                break

    # 检查是否有超时
    for item in history:
        if item.get("role") == "tool":
            content = str(item.get("content", ""))
            if "timed out" in content.lower():
                score -= 1

    return max(0, score)


def _check_controllability(agent, tool_calls):
    """可控性评分。"""
    score = 10  # 默认满分，扣分制

    # 检查是否在步数限制内
    if len(tool_calls) > agent.max_steps:
        score -= 5

    # 检查是否有危险命令被拦截
    for item in tool_calls:
        content = str(item.get("content", ""))
        if "dangerous command" in content.lower():
            score -= 0  # 拦截是好事，不扣分

    return max(0, score)


def _check_ux(response, task):
    """用户体验评分。"""
    if not response or len(response.strip()) == 0:
        return 0

    score = 5  # 基础分

    # 回答长度合理
    if 50 < len(response) < 2000:
        score += 2

    # 包含结构化信息
    if any(marker in response for marker in ["\n", "-", "1.", "•", ":"]):
        score += 1

    # 包含关键词
    for kw in task.get("expected_in_response", []):
        if kw.lower() in response.lower():
            score += 1
            break

    return min(10, score)


def _check_baseline_completeness(task, response):
    """Baseline 完整性评分。"""
    if not response or len(response.strip()) == 0:
        return 0

    score = 2  # 有回答

    # 包含预期关键词
    for kw in task.get("expected_in_response", []):
        if kw.lower() in (response or "").lower():
            score += 2

    # 回答长度
    if len(response) > 100:
        score += 1

    return min(10, score)


def _check_baseline_ux(response):
    """Baseline 用户体验评分。"""
    if not response or len(response.strip()) == 0:
        return 0

    score = 5

    if 50 < len(response) < 2000:
        score += 2

    if any(marker in response for marker in ["\n", "-", "1.", "•", ":"]):
        score += 1

    return min(10, score)
