"""CLI argument handling and guided REPL entrypoint for Auto Issue Fix."""

from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

from ..provider_registry import provider_choices
from .config import (
    AUTO_ISSUE_FIX_MODES,
    AUTO_REVIEW_MODES,
    AutoIssueFixConfig,
    AutoIssueFixRunRecord,
)
from .evidence import write_evidence
from .runner import run_auto_issue_fix


def _split_csv(values: list[str] | None, default: tuple[str, ...]) -> tuple[str, ...]:
    items: list[str] = []
    for value in values or ():
        items.extend(part.strip() for part in str(value).split(",") if part.strip())
    return tuple(items) or default


def build_auto_issue_fix_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repo-harness auto-issue-fix",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Prepare a governed Auto Issue Fix run with RepoHarness evidence artifacts.",
    )
    parser.add_argument("--repo", default="", help="GitHub repository URL or owner/name.")
    parser.add_argument("--issue", type=int, default=None, help="Issue number to fix.")
    parser.add_argument("--discover", action="store_true", help="Discover a candidate issue instead of using --issue.")
    parser.add_argument("--source", choices=("trending", "repo"), default="trending", help="Discovery source.")
    parser.add_argument("--criteria", action="append", default=[], help="Comma-separated discovery criteria.")
    parser.add_argument("--mode", choices=AUTO_ISSUE_FIX_MODES, default="review-gated", help="Automation mode.")
    parser.add_argument("--evidence-dir", default=None, help="Evidence output directory.")
    parser.add_argument("--workspace-root", default=".", help="Workspace root for the Auto Issue Fix run.")
    parser.add_argument("--workdir", default=None, help="Isolated clone directory for live Auto Issue Fix execution.")
    parser.add_argument("--test-command", action="append", default=[], help="Validation command to record or run.")
    parser.add_argument("--dry-run", action="store_true", help="Generate the evidence plan without clone, push, or PR side effects.")
    parser.add_argument("--include-local-paths", action="store_true", help="Include local absolute paths in evidence artifacts.")
    parser.add_argument("--auto-review", choices=AUTO_REVIEW_MODES, default="required", help="Automatic review gate policy.")
    parser.add_argument("--max-review-repairs", type=int, default=2, help="Maximum bounded repair loops after a needs_fix verdict.")
    parser.add_argument("--resume", default="", help="Resume from a previous Auto Issue Fix run id when live runner support is enabled.")
    parser.add_argument("--provider", choices=provider_choices(), default="", help="Model backend for live fix turns.")
    parser.add_argument("--model", default=None, help="Model name override for live fix turns.")
    parser.add_argument("--base-url", default=None, help="OpenAI/Anthropic-compatible base URL override.")
    parser.add_argument("--host", default=None, help="Ollama host override.")
    parser.add_argument("--temperature", type=float, default=0.2, help="Model temperature for live fix turns.")
    parser.add_argument("--top-p", type=float, default=0.9, help="Ollama top_p for live fix turns.")
    parser.add_argument("--ollama-timeout", type=int, default=300, help="Ollama request timeout.")
    parser.add_argument("--openai-timeout", type=int, default=300, help="OpenAI/Anthropic-compatible request timeout.")
    parser.add_argument("--max-steps", type=int, default=50, help="RepoHarness max tool loop steps for live fix turns.")
    parser.add_argument("--max-new-tokens", type=int, default=8192, help="RepoHarness max new tokens for live fix turns.")
    parser.add_argument("--commit-message", default="", help="Commit message override for live Auto Issue Fix execution.")
    parser.add_argument(
        "--confirm-maintainer-access",
        action="store_true",
        help="Confirm that you maintain or are explicitly authorized to submit changes to the target repository.",
    )
    return parser


def config_from_args(args) -> AutoIssueFixConfig:
    return AutoIssueFixConfig(
        repo=str(args.repo or ""),
        issue=args.issue,
        discover=bool(args.discover),
        source=str(args.source or "trending"),
        criteria=_split_csv(args.criteria, ("bug", "test")),
        mode=str(args.mode or "review-gated"),
        evidence_dir=Path(args.evidence_dir) if args.evidence_dir else None,
        workspace_root=Path(args.workspace_root or "."),
        workdir=Path(args.workdir) if args.workdir else None,
        dry_run=bool(args.dry_run),
        include_local_paths=bool(args.include_local_paths),
        test_commands=tuple(str(item) for item in args.test_command or ()),
        auto_review=str(args.auto_review or "required"),
        max_review_repairs=int(args.max_review_repairs),
        resume=str(args.resume or ""),
        provider=str(args.provider or ""),
        model=args.model,
        base_url=args.base_url,
        host=args.host,
        temperature=float(args.temperature),
        top_p=float(args.top_p),
        ollama_timeout=int(args.ollama_timeout),
        openai_timeout=int(args.openai_timeout),
        max_steps=int(args.max_steps),
        max_new_tokens=int(args.max_new_tokens),
        commit_message=str(args.commit_message or ""),
        maintainer_access_confirmed=bool(args.confirm_maintainer_access),
    )


def run_auto_issue_fix_argv(argv: list[str] | None = None) -> tuple[int, str, AutoIssueFixRunRecord | None]:
    parser = build_auto_issue_fix_arg_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0), "", None
    config = config_from_args(args)
    try:
        record = _run_auto_issue_fix_for_argv(config)
    except ValueError as exc:
        return 2, f"auto-issue-fix: {exc}", None
    write_evidence(record, include_local_paths=config.include_local_paths)
    lines = []
    lines.append("Risk notice: " + config.risk_notice())
    if config.dry_run:
        lines.append("Auto Issue Fix safe preview complete")
    elif record.status == "completed":
        lines.append("Auto Issue Fix draft PR created")
    elif record.status == "paused":
        lines.append("Auto Issue Fix paused for review-gated confirmation")
    else:
        lines.append("Auto Issue Fix evidence generated; live execution did not create a PR")
    lines.append(f"Evidence: {record.evidence_dir}")
    return (0 if config.dry_run or record.status == "completed" else 1), "\n".join(lines), record


def _run_auto_issue_fix_for_argv(config: AutoIssueFixConfig) -> AutoIssueFixRunRecord:
    facade = sys.modules.get("repo_harness.auto_issue_fix")
    facade_runner = getattr(facade, "run_auto_issue_fix", None) if facade is not None else None
    if facade_runner is not None and facade_runner is not run_auto_issue_fix:
        return facade_runner(config)
    return run_auto_issue_fix(config)


def _run_auto_issue_fix_argv_for_repl(argv: list[str]) -> tuple[int, str, AutoIssueFixRunRecord | None]:
    facade = sys.modules.get("repo_harness.auto_issue_fix")
    facade_runner = getattr(facade, "run_auto_issue_fix_argv", None) if facade is not None else None
    if facade_runner is not None and facade_runner is not run_auto_issue_fix_argv:
        return facade_runner(argv)
    return run_auto_issue_fix_argv(argv)


def guided_auto_issue_fix_argv(workspace_root: Path | str, input_func=input) -> tuple[list[str], str] | tuple[None, str]:
    print("Auto Issue Fix guided mode")
    print("Mode: press Enter for the recommended review-gated live execution, type dry-run for safe preview, or draft-auto for draft PR automation.")
    mode_value = input_func("Mode [review-gated/draft-auto/dry-run]: ").strip().lower()
    dry_run = mode_value == "dry-run"
    mode = "draft-auto" if mode_value == "draft-auto" else "review-gated"
    repo = input_func("Repository (owner/name or GitHub URL; blank to discover from trending): ").strip()
    if repo:
        issue_text = input_func("Issue number (blank to discover within this repository): ").strip()
    else:
        issue_text = ""
    test_command = input_func("Test command (optional; blank to infer): ").strip()
    confirm_maintainer_access = False
    if not dry_run:
        confirm_answer = input_func(
            "Confirm maintainer access or explicit authorization for live commit/push/draft PR? [y/N]: "
        ).strip().lower()
        confirm_maintainer_access = confirm_answer in {"y", "yes"}
    if repo and issue_text:
        if not issue_text.isdigit():
            return None, "auto-issue-fix: issue number must be a positive integer"
        argv = ["--repo", repo, "--issue", issue_text, "--mode", mode, "--workspace-root", str(workspace_root)]
    elif repo:
        argv = [
            "--discover",
            "--source",
            "repo",
            "--repo",
            repo,
            "--criteria",
            "bug,test",
            "--mode",
            mode,
            "--workspace-root",
            str(workspace_root),
        ]
    else:
        argv = [
            "--discover",
            "--source",
            "trending",
            "--criteria",
            "bug,test",
            "--mode",
            mode,
            "--workspace-root",
            str(workspace_root),
        ]
    if dry_run:
        argv.append("--dry-run")
    if test_command:
        argv.extend(["--test-command", test_command])
    if confirm_maintainer_access:
        argv.append("--confirm-maintainer-access")
    summary = " ".join(shlex.quote(item) for item in ["repo-harness", "auto-issue-fix", *argv])
    access_note = (
        "Maintainer access confirmed for live execution."
        if confirm_maintainer_access
        else "Confirm maintainer access was not provided; live execution will stop before clone/model tools/commit/push/PR."
    )
    return argv, (
        "Auto Issue Fix guided command prepared:\n"
        f"{summary}\n"
        f"{access_note}\n"
        "Reminder: review-gated pauses before commit, push, and draft PR creation."
    )


def handle_auto_issue_fix_repl_command(
    body: str,
    workspace_root: Path | str = ".",
    *,
    interactive: bool = False,
    input_func=input,
) -> tuple[int, str]:
    body = str(body or "").strip()
    if not body:
        if not interactive:
            return (
                2,
                "usage: /auto-issue-fix --repo owner/name --issue 123 [--dry-run]\n"
                "Run `/auto-issue-fix` in the interactive REPL to use guided mode.",
            )
        guided_argv, prefix = guided_auto_issue_fix_argv(workspace_root, input_func=input_func)
        if guided_argv is None:
            return 2, prefix
        argv = guided_argv
        prefix += "\n"
    else:
        try:
            argv = shlex.split(body)
        except ValueError as exc:
            return 2, f"auto-issue-fix: could not parse arguments: {exc}"
        if "--workspace-root" not in argv:
            argv.extend(["--workspace-root", str(workspace_root)])
        prefix = ""
    code, output, _record = _run_auto_issue_fix_argv_for_repl(argv)
    return code, prefix + output


def handle_auto_issue_fix_command(argv: list[str] | None = None) -> int:
    code, output, _record = _run_auto_issue_fix_argv_for_repl(argv or [])
    if output:
        stream = sys.stderr if code == 2 else sys.stdout
        print(output, file=stream)
    return code
