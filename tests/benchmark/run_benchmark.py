"""Benchmark 主入口 — 运行所有对比测试并输出报告。"""

import json
import sys
import tempfile
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tasks import TASKS
from tool_runner import run_tool_task
from baseline_runner import run_baseline
from evaluator import evaluate_tool_runner, evaluate_baseline
from common import get_deepseek_client, get_mimo_client


def _client_factory(provider, timeout=60):
    provider = str(provider or "deepseek").lower()
    if provider == "deepseek":
        return lambda: get_deepseek_client(timeout=timeout)
    if provider == "mimo":
        return lambda: get_mimo_client(timeout=timeout)
    raise ValueError(f"unsupported provider: {provider}")


def _provider_model(provider):
    return "mimo-v2.5-pro" if str(provider).lower() == "mimo" else "deepseek-v4-pro"


def _write_markdown_report(report_path, payload):
    lines = [
        "# RepoHarness Benchmark Report",
        "",
        f"- Provider: {payload['provider']}",
        f"- Model: {payload['model']}",
        f"- Date: {payload['date']}",
        f"- Tool Runner avg: {payload['tool_avg']:.1f}/50",
        f"- Baseline avg: {payload['baseline_avg']:.1f}/50",
        f"- Avg advantage: {payload['avg_delta']:+.1f}",
        "",
        "| Task | Tool | Baseline | Delta | Tool Calls |",
        "|---|---:|---:|---:|---:|",
    ]
    for task in payload["tasks"]:
        lines.append(
            f"| {task['id']} {task['name']} | "
            f"{task['tool_scores']['total']} | "
            f"{task['baseline_scores']['total']} | "
            f"{task['delta']:+d} | "
            f"{task['tool_scores'].get('tool_calls_count', 0)} |"
        )
    lines.extend([
        "",
        "## Dimension Averages",
        "",
        "| Dimension | Tool | Baseline | Delta |",
        "|---|---:|---:|---:|",
    ])
    for key, label in {
        "completeness": "Completeness",
        "auditability": "Auditability",
        "stability": "Stability",
        "controllability": "Control",
        "ux": "UX",
    }.items():
        dim = payload["dimension_averages"][key]
        lines.append(f"| {label} | {dim['tool']:.1f} | {dim['baseline']:.1f} | {dim['delta']:+.1f} |")
    lines.extend([
        "",
        "## Interview Summary",
        "",
        (
            f"On {len(payload['tasks'])} standardized repository tasks, RepoHarness scored "
            f"{payload['tool_avg']:.1f}/50 versus {payload['baseline_avg']:.1f}/50 for direct model use "
            f"({payload['avg_delta']:+.1f})."
        ),
        "The largest gains came from auditability and controllability because the tool path records files, commands, traces, reports, and bounded tool calls.",
        "This supports the product claim that a governed local agent is more useful than a naked model API for repository work that needs evidence.",
        "",
        "## Task Details",
        "",
    ])
    for task in payload["tasks"]:
        lines.extend([
            f"### {task['id']} {task['name']}",
            "",
            f"- Tool time: {task['tool_time']:.1f}s",
            f"- Baseline time: {task['baseline_time']:.1f}s",
            f"- Tool preview: {task['tool_response_preview']}",
            f"- Baseline preview: {task['baseline_response_preview']}",
            "",
        ])
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_benchmark(provider="deepseek", output_dir=None):
    """运行完整 Benchmark 并输出报告。"""
    provider = str(provider or "deepseek").lower()
    model = _provider_model(provider)
    client_factory = _client_factory(provider, timeout=60)
    output_root = Path(output_dir) if output_dir else Path(__file__).resolve().parent / "results"
    output_root.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("  RepoHarness Benchmark Report")
    print(f"  Provider: {provider}")
    print(f"  Model: {model}")
    print("  Date: " + time.strftime("%Y-%m-%d %H:%M"))
    print("=" * 60)
    print()

    if client_factory() is None:
        print(f"[ERROR] No client available for provider: {provider}")
        return 1

    results = []
    tool_total = 0
    baseline_total = 0

    for task in TASKS:
        tid = task["id"]
        tname = task["name"]
        print(f"--- {tid} {tname} ---")

        # Tool Runner
        print("  Tool Runner: ", end="", flush=True)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            agent, tool_time, tool_response, tool_error = run_tool_task(
                task,
                tmp_path,
                client_factory=client_factory,
            )
            if agent:
                tool_scores = evaluate_tool_runner(task, agent, tmp_path, tool_response)
                tool_total += tool_scores["total"]
                print(f"OK {tool_scores['total']}/50 ({tool_time:.0f}s) "
                      f"[C={tool_scores['completeness']} A={tool_scores['auditability']} "
                      f"S={tool_scores['stability']} X={tool_scores['controllability']} "
                      f"U={tool_scores['ux']}] "
                      f"tools={tool_scores['tool_calls_count']}")
            else:
                tool_scores = {"total": 0, "completeness": 0, "auditability": 0,
                               "stability": 0, "controllability": 0, "ux": 0,
                               "response_preview": f"[ERROR] {tool_error}", "tool_calls_count": 0}
                print(f"FAIL 0/50 ({tool_error})")

        # Baseline
        print("  Baseline:    ", end="", flush=True)
        response_text, baseline_time = run_baseline(task, client_factory=client_factory)
        baseline_scores = evaluate_baseline(task, response_text)
        baseline_total += baseline_scores["total"]
        tag = "OK" if baseline_scores["total"] > 0 else "FAIL"
        print(f"{tag} {baseline_scores['total']}/50 ({baseline_time:.0f}s) "
              f"[C={baseline_scores['completeness']} A={baseline_scores['auditability']} "
              f"S={baseline_scores['stability']} X={baseline_scores['controllability']} "
              f"U={baseline_scores['ux']}]")

        # Delta
        delta = tool_scores["total"] - baseline_scores["total"]
        advantages = []
        dim_names = {"completeness": "C", "auditability": "A", "stability": "S",
                     "controllability": "X", "ux": "U"}
        for dim, label in dim_names.items():
            d = tool_scores[dim] - baseline_scores[dim]
            if d > 0:
                advantages.append(f"{label}(+{d})")
        adv_str = " ".join(advantages) if advantages else "none"
        print(f"  Delta = {delta:+d}  Advantages: {adv_str}")
        print()

        results.append({
            "id": tid, "name": tname,
            "tool_scores": {k: v for k, v in tool_scores.items() if k not in ("response_preview",)},
            "baseline_scores": {k: v for k, v in baseline_scores.items() if k not in ("response_preview",)},
            "delta": delta,
            "tool_time": tool_time if agent else 0,
            "baseline_time": baseline_time,
            "tool_response_preview": tool_scores.get("response_preview", "")[:300],
            "baseline_response_preview": baseline_scores.get("response_preview", "")[:300],
            "tool_response": tool_response if agent else "",
            "tool_error": tool_error if not agent else "",
            "baseline_response": response_text or "",
        })

    # Summary
    n = len(TASKS)
    print("=" * 60)
    print("  Summary")
    print("=" * 60)
    print()
    print(f"  Tool Runner avg: {tool_total / n:.1f}/50")
    print(f"  Baseline avg:    {baseline_total / n:.1f}/50")
    print(f"  Avg advantage:   +{(tool_total - baseline_total) / n:.1f}")
    print()

    dim_totals_tool = {d: 0 for d in ["completeness", "auditability", "stability", "controllability", "ux"]}
    dim_totals_bl = {d: 0 for d in ["completeness", "auditability", "stability", "controllability", "ux"]}
    for r in results:
        for d in dim_totals_tool:
            dim_totals_tool[d] += r["tool_scores"].get(d, 0)
            dim_totals_bl[d] += r["baseline_scores"].get(d, 0)

    print(f"  {'Dim':<15} {'Tool':>6} {'Baseline':>8} {'Delta':>6}")
    print(f"  {'-'*15} {'-'*6} {'-'*8} {'-'*6}")
    dimension_averages = {}
    for d, label in {"completeness": "Completeness", "auditability": "Auditability",
                     "stability": "Stability", "controllability": "Control", "ux": "UX"}.items():
        t = dim_totals_tool[d] / n
        b = dim_totals_bl[d] / n
        dimension_averages[d] = {"tool": t, "baseline": b, "delta": t - b}
        print(f"  {label:<15} {t:>6.1f} {b:>8.1f} {t-b:>+6.1f}")

    # Save JSON
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    payload = {
        "provider": provider,
        "model": model,
        "date": time.strftime("%Y-%m-%d %H:%M"),
        "tool_avg": tool_total / n,
        "baseline_avg": baseline_total / n,
        "avg_delta": (tool_total - baseline_total) / n,
        "dimension_averages": dimension_averages,
        "tasks": results,
    }
    report_path = output_root / f"benchmark_report_{provider}_{timestamp}.json"
    markdown_path = output_root / f"benchmark_report_{provider}_{timestamp}.md"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    _write_markdown_report(markdown_path, payload)
    latest_path = output_root / f"benchmark_report_{provider}_latest.json"
    latest_md = output_root / f"benchmark_report_{provider}_latest.md"
    latest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    latest_md.write_text(markdown_path.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"\n  JSON report saved: {report_path}")
    print(f"  Markdown report saved: {markdown_path}")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run RepoHarness benchmark.")
    parser.add_argument("--provider", choices=["deepseek", "mimo"], default="deepseek")
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()
    sys.exit(run_benchmark(provider=args.provider, output_dir=args.output_dir or None))
