"""Auto PR orchestration primitives.

Auto PR is a governed workflow layer for turning GitHub issues into auditable
PR-ready evidence. The current implementation is the framework and safe preview
mode: it creates portable evidence, review gates, checkpoints, and redacted
reports without performing live clone, push, or PR creation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import time
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path


AUTO_PR_MODES = ("review-gated", "draft-auto")
AUTO_REVIEW_MODES = ("required",)
AUTO_REVIEW_VERDICTS = ("pass", "needs_fix", "block")
AUTO_REVIEW_STAGES = (
    ("task", "任务审查", "确认仓库、issue、目标、边界和风险。"),
    ("plan", "计划审查", "检查执行计划、写入范围、测试策略和失败回退。"),
    ("context", "上下文审查", "确认必要文件和 issue 背景已经进入后续执行上下文。"),
    ("diff", "Diff 审查", "检查是否存在无关改动、生成物污染或大范围重写。"),
    ("tests", "测试审查", "检查 baseline、修复后测试和失败日志是否匹配 issue。"),
    ("security", "安全审查", "检查 secret、路径泄露、危险命令、越权写入和供应链风险。"),
    ("pr-readiness", "PR 准备审查", "检查 PR 描述、证据包、变更摘要、测试命令和风险说明。"),
)
SECRET_PATTERNS = (
    re.compile(r"\b(?:sk|gho|ghp|github_pat)[_-][A-Za-z0-9_=-]{6,}"),
    re.compile(r"\b(?:OPENAI_API_KEY|GITHUB_TOKEN|GH_TOKEN|MIMO_API_KEY|COOKIE|cookie)\s*=\s*[^\s]+", re.I),
    re.compile(r"\b(?:token|api[_-]?key|cookie)\s*[:=]\s*[^\s]+", re.I),
)


@dataclass(frozen=True)
class AutoPrConfig:
    repo: str = ""
    issue: int | None = None
    discover: bool = False
    source: str = "trending"
    criteria: tuple[str, ...] = ("bug", "test")
    mode: str = "review-gated"
    evidence_dir: Path | None = None
    workspace_root: Path | None = None
    dry_run: bool = False
    include_local_paths: bool = False
    test_commands: tuple[str, ...] = ()
    auto_review: str = "required"
    max_review_repairs: int = 2
    resume: str = ""

    def validate(self) -> None:
        if self.mode not in AUTO_PR_MODES:
            raise ValueError(f"mode must be one of: {', '.join(AUTO_PR_MODES)}")
        if self.auto_review not in AUTO_REVIEW_MODES:
            raise ValueError("auto-review must be required")
        if self.mode == "draft-auto" and self.auto_review != "required":
            raise ValueError("draft-auto cannot disable automatic review gates")
        if self.max_review_repairs < 0:
            raise ValueError("--max-review-repairs must be zero or greater")
        if not self.discover and (not self.repo or self.issue is None):
            raise ValueError("auto-pr requires --repo and --issue unless --discover is set")
        if self.discover and self.repo and self.issue is not None:
            raise ValueError("--discover cannot be combined with both --repo and --issue")

    def risk_notice(self) -> str:
        if self.mode == "draft-auto":
            return (
                "draft-auto skips human pauses only after automatic review gates pass. "
                "A block verdict stops the run and writes fallback evidence instead of creating a draft PR."
            )
        return (
            "review-gated uses the same automatic review gates, then pauses for human confirmation "
            "at high-risk checkpoints."
        )


@dataclass(frozen=True)
class AutoPrReviewGate:
    stage: str
    title: str
    verdict: str
    summary: str
    required_action: str = ""
    repair_attempts: int = 0

    def validate(self) -> None:
        if self.verdict not in AUTO_REVIEW_VERDICTS:
            raise ValueError(f"review verdict must be one of: {', '.join(AUTO_REVIEW_VERDICTS)}")


@dataclass(frozen=True)
class AutoPrRunRecord:
    run_id: str
    mode: str
    repo: str
    issue: int | None
    workspace_path: str
    evidence_dir: str
    status: str
    summary: str
    tests: list[dict]
    pr_url: str = ""
    fallback_reason: str = ""
    selected_issue_url: str = ""
    changed_paths: tuple[str, ...] = ()
    auto_review: str = "required"
    max_review_repairs: int = 2
    review_gates: tuple[AutoPrReviewGate, ...] = ()
    resume_from: str = ""


def redact_text(text: str) -> str:
    redacted = str(text)
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("<redacted>", redacted)
    return redacted


def portable_path(path: str, placeholder: str, include_local_paths: bool = False) -> str:
    if include_local_paths:
        return redact_text(path)
    return placeholder


def default_run_id() -> str:
    return "auto_pr_" + time.strftime("%Y%m%d_%H%M%S")


def default_evidence_dir(workspace_root: Path, run_id: str) -> Path:
    return workspace_root / ".repo-harness" / "auto-pr" / run_id


def _public_record(record: AutoPrRunRecord, include_local_paths: bool) -> dict:
    data = asdict(record)
    data["workspace_path"] = portable_path(record.workspace_path, "<workspace>", include_local_paths)
    data["evidence_dir"] = portable_path(record.evidence_dir, "<evidence_dir>", include_local_paths)
    return json.loads(redact_text(json.dumps(data, ensure_ascii=False)))


def build_preview_review_gates(config: AutoPrConfig, status: str) -> tuple[AutoPrReviewGate, ...]:
    verdict = "pass" if status == "planned" else "block"
    action = (
        "dry-run preview recorded; live execution remains disabled in this version"
        if verdict == "pass"
        else "stop before live GitHub side effects and generate fallback evidence"
    )
    gates = []
    for stage, title, description in AUTO_REVIEW_STAGES:
        gates.append(
            AutoPrReviewGate(
                stage=stage,
                title=title,
                verdict=verdict,
                summary=f"{description} Current mode is {config.mode}; automatic review is {config.auto_review}.",
                required_action=action,
            )
        )
    return tuple(gates)


def _review_gate_lines(review_gates: list[dict]) -> str:
    if not review_gates:
        return "- (none recorded)"
    return "\n".join(
        f"- `{item.get('stage', '-')}` {item.get('title', '')}: {item.get('verdict', '-')}"
        for item in review_gates
    )


def review_gates_block_reason(review_gates: tuple[AutoPrReviewGate, ...], max_review_repairs: int) -> str:
    for gate in review_gates:
        gate.validate()
        if gate.verdict == "block":
            return f"{gate.stage} review gate blocked the run"
        if gate.verdict == "needs_fix" and gate.repair_attempts >= max_review_repairs:
            return f"{gate.stage} review gate exceeded max review repairs"
    return ""


def render_evidence_templates(record: AutoPrRunRecord, include_local_paths: bool = False) -> dict[str, str]:
    public_record = _public_record(record, include_local_paths)
    repo = public_record.get("repo") or "<repo>"
    issue = public_record.get("issue")
    issue_ref = f"#{issue}" if issue is not None else "(auto-discovered)"
    tests = public_record.get("tests") or []
    test_lines = "\n".join(
        f"- `{item.get('command', '-')}`: {item.get('status', '-')}" for item in tests
    ) or "- (not run)"
    fallback = public_record.get("fallback_reason") or ""
    fallback_block = f"\n\n## Fallback\n\nPR creation blocked: {fallback}\n" if fallback else ""
    status = public_record.get("status", "")
    pr_url = public_record.get("pr_url") or ""
    review_gates = public_record.get("review_gates") or []
    review_lines = _review_gate_lines(review_gates)

    run_record = f"""# Auto PR Run Record

## Summary

- Run ID: `{public_record['run_id']}`
- Mode: `{public_record['mode']}`
- Repository: `{repo}`
- Issue: `{issue_ref}`
- Status: `{status}`
- Workspace: `{public_record['workspace_path']}`
- Evidence directory: `{public_record['evidence_dir']}`
- PR URL: `{pr_url or '(none)'}`
- Automatic review: `{public_record.get('auto_review', 'required')}`
- Max review repairs: `{public_record.get('max_review_repairs', 2)}`

## Result

{public_record.get('summary') or '(none)'}

## Automatic Review Gates

{review_lines}

## Tests

{test_lines}
{fallback_block}
## Changed Paths

{chr(10).join(f'- `{path}`' for path in public_record.get('changed_paths', ())) or '- (none recorded)'}
"""

    if fallback:
        pr_body = f"""# PR-ready fallback

Auto PR did not create a pull request because: {fallback}

Repository: {repo}
Issue: {issue_ref}
"""
    else:
        pr_body = f"""Fixes {repo}{issue_ref if issue is not None else ''}

## Summary

{public_record.get('summary') or 'Auto PR prepared this change with RepoHarness evidence gates.'}

## Review Gates

{review_lines}

## Validation

{test_lines}
"""

    formal_summary = f"""# RepoHarness Auto PR Formal Report Summary

This run is an Auto-PR assisted workflow, not a claim that model output is trusted without governance. RepoHarness coordinates scoped file access, evidence generation, test gates, and PR preparation while preserving auditability.

- Repository: `{repo}`
- Issue: `{issue_ref}`
- Mode: `{public_record['mode']}`
- Status: `{status}`
- Evidence: `{public_record['evidence_dir']}`
- PR: `{pr_url or '(not created)'}`
- Automatic review: `{public_record.get('auto_review', 'required')}`

## Review Gates

{review_lines}
"""

    rendered = {
        "run-record.md": redact_text(run_record),
        "pr-body.md": redact_text(pr_body),
        "formal-report-summary.md": redact_text(formal_summary),
        "run-record.json": json.dumps(public_record, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
    }
    if fallback:
        rendered["pr-ready-fallback.md"] = redact_text(
            f"""# PR-ready fallback

Auto PR stopped before creating a pull request.

- Repository: `{repo}`
- Issue: `{issue_ref}`
- Reason: {fallback}
- Evidence: `{public_record['evidence_dir']}`
"""
        )
    return rendered


def write_evidence(record: AutoPrRunRecord, include_local_paths: bool = False) -> dict[str, Path]:
    evidence_dir = Path(record.evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for name, content in render_evidence_templates(record, include_local_paths=include_local_paths).items():
        path = evidence_dir / name
        path.write_text(content, encoding="utf-8")
        written[name] = path
    public_record = _public_record(record, include_local_paths)
    reviews_dir = evidence_dir / "reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    decisions = []
    for gate in public_record.get("review_gates", ()):
        stage = str(gate.get("stage", "unknown"))
        json_path = reviews_dir / f"review-{stage}.json"
        md_path = reviews_dir / f"review-{stage}.md"
        json_path.write_text(json.dumps(gate, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        md_path.write_text(
            redact_text(
                f"""# {gate.get('title', stage)}

- Stage: `{stage}`
- Verdict: `{gate.get('verdict', '-')}`
- Required action: {gate.get('required_action') or '(none)'}

{gate.get('summary') or ''}
"""
            ),
            encoding="utf-8",
        )
        written[str(json_path.relative_to(evidence_dir))] = json_path
        written[str(md_path.relative_to(evidence_dir))] = md_path
        decisions.append(
            {
                "run_id": public_record.get("run_id"),
                "stage": stage,
                "verdict": gate.get("verdict"),
                "required_action": gate.get("required_action", ""),
            }
        )
    decision_log_path = evidence_dir / "decision-log.jsonl"
    decision_log_path.write_text(
        "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in decisions),
        encoding="utf-8",
    )
    written["decision-log.jsonl"] = decision_log_path
    checkpoint_path = evidence_dir / "checkpoint.json"
    checkpoint = {
        "run_id": public_record.get("run_id"),
        "mode": public_record.get("mode"),
        "status": public_record.get("status"),
        "resume_from": public_record.get("resume_from") or "",
        "next_action": "live execution disabled; use evidence for review or rerun with a future live runner",
    }
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    written["checkpoint.json"] = checkpoint_path
    return written


def _split_csv(values: list[str] | None, default: tuple[str, ...]) -> tuple[str, ...]:
    items: list[str] = []
    for value in values or ():
        items.extend(part.strip() for part in str(value).split(",") if part.strip())
    return tuple(items) or default


def build_auto_pr_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repo-harness auto-pr",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Prepare a governed Auto PR run with RepoHarness evidence artifacts.",
    )
    parser.add_argument("--repo", default="", help="GitHub repository URL or owner/name.")
    parser.add_argument("--issue", type=int, default=None, help="Issue number to fix.")
    parser.add_argument("--discover", action="store_true", help="Discover a candidate issue instead of using --issue.")
    parser.add_argument("--source", choices=("trending", "repo"), default="trending", help="Discovery source.")
    parser.add_argument("--criteria", action="append", default=[], help="Comma-separated discovery criteria.")
    parser.add_argument("--mode", choices=AUTO_PR_MODES, default="review-gated", help="Automation mode.")
    parser.add_argument("--evidence-dir", default=None, help="Evidence output directory.")
    parser.add_argument("--workspace-root", default=".", help="Workspace root for the Auto PR run.")
    parser.add_argument("--test-command", action="append", default=[], help="Validation command to record or run.")
    parser.add_argument("--dry-run", action="store_true", help="Generate the evidence plan without clone, push, or PR side effects.")
    parser.add_argument("--include-local-paths", action="store_true", help="Include local absolute paths in evidence artifacts.")
    parser.add_argument("--auto-review", choices=AUTO_REVIEW_MODES, default="required", help="Automatic review gate policy.")
    parser.add_argument("--max-review-repairs", type=int, default=2, help="Maximum bounded repair loops after a needs_fix verdict.")
    parser.add_argument("--resume", default="", help="Resume from a previous Auto PR run id when live runner support is enabled.")
    return parser


def config_from_args(args) -> AutoPrConfig:
    return AutoPrConfig(
        repo=str(args.repo or ""),
        issue=args.issue,
        discover=bool(args.discover),
        source=str(args.source or "trending"),
        criteria=_split_csv(args.criteria, ("bug", "test")),
        mode=str(args.mode or "review-gated"),
        evidence_dir=Path(args.evidence_dir) if args.evidence_dir else None,
        workspace_root=Path(args.workspace_root or "."),
        dry_run=bool(args.dry_run),
        include_local_paths=bool(args.include_local_paths),
        test_commands=tuple(str(item) for item in args.test_command or ()),
        auto_review=str(args.auto_review or "required"),
        max_review_repairs=int(args.max_review_repairs),
        resume=str(args.resume or ""),
    )


def run_auto_pr(config: AutoPrConfig) -> AutoPrRunRecord:
    config.validate()
    workspace_root = Path(config.workspace_root or ".").resolve()
    run_id = default_run_id()
    evidence_dir = Path(config.evidence_dir).resolve() if config.evidence_dir else default_evidence_dir(workspace_root, run_id)
    status = "planned" if config.dry_run else "blocked"
    fallback_reason = "" if config.dry_run else "live clone/fix/test/push/PR runner is not enabled in this version"
    issue_url = ""
    if config.repo and config.issue is not None:
        repo_ref = config.repo.rstrip("/")
        issue_url = f"{repo_ref}/issues/{config.issue}" if repo_ref.startswith("http") else f"https://github.com/{repo_ref}/issues/{config.issue}"
    tests = [
        {"command": command, "status": "not_run" if config.dry_run else "blocked"}
        for command in config.test_commands
    ]
    summary = (
        "Auto PR safe preview created a portable evidence scaffold with automatic review gates."
        if config.dry_run
        else "Auto PR live execution is blocked until the real execution runner is enabled."
    )
    review_gates = build_preview_review_gates(config, status)
    return AutoPrRunRecord(
        run_id=run_id,
        mode=config.mode,
        repo=config.repo or f"auto-discover:{config.source}",
        issue=config.issue,
        workspace_path=str(workspace_root),
        evidence_dir=str(evidence_dir),
        status=status,
        summary=summary,
        tests=tests,
        fallback_reason=fallback_reason,
        selected_issue_url=issue_url,
        auto_review=config.auto_review,
        max_review_repairs=config.max_review_repairs,
        review_gates=review_gates,
        resume_from=config.resume,
    )


def run_auto_pr_argv(argv: list[str] | None = None) -> tuple[int, str, AutoPrRunRecord | None]:
    parser = build_auto_pr_arg_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0), "", None
    config = config_from_args(args)
    try:
        record = run_auto_pr(config)
    except ValueError as exc:
        return 2, f"auto-pr: {exc}", None
    write_evidence(record, include_local_paths=config.include_local_paths)
    lines = []
    lines.append("Risk notice: " + config.risk_notice())
    lines.append("Auto PR safe preview complete" if config.dry_run else "Auto PR evidence generated; live execution blocked")
    lines.append(f"Evidence: {record.evidence_dir}")
    return (0 if config.dry_run else 1), "\n".join(lines), record


def handle_auto_pr_repl_command(body: str, workspace_root: Path | str = ".") -> tuple[int, str]:
    body = str(body or "").strip()
    if not body:
        argv = ["--discover", "--dry-run", "--workspace-root", str(workspace_root)]
        prefix = (
            "Auto PR guided mode: no repository or issue was provided, so RepoHarness prepared "
            "an automatic-discovery safe preview. Provide `/auto-pr --repo owner/name --issue 123` "
            "to target a specific issue.\n"
        )
    else:
        try:
            argv = shlex.split(body)
        except ValueError as exc:
            return 2, f"auto-pr: could not parse arguments: {exc}"
        if "--workspace-root" not in argv:
            argv.extend(["--workspace-root", str(workspace_root)])
        if "--dry-run" not in argv:
            argv.append("--dry-run")
        prefix = ""
    code, output, _record = run_auto_pr_argv(argv)
    return code, prefix + output


def handle_auto_pr_command(argv: list[str] | None = None) -> int:
    code, output, _record = run_auto_pr_argv(argv)
    if output:
        stream = os.sys.stderr if code == 2 else os.sys.stdout
        print(output, file=stream)
    return code
