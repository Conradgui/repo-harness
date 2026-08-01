"""Auto Issue Fix execution runner."""

from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path

from repo_harness.config import resolve_runtime_config

from .config import (
    AutoIssueFixConfig,
    AutoIssueFixIssue,
    AutoIssueFixReviewGate,
    AutoIssueFixRunRecord,
    LiveRunContext,
)
from .evidence import (
    build_preview_review_gates,
    default_evidence_dir,
    default_run_id,
    default_workdir,
    render_evidence_templates,
    review_gates_block_reason,
    write_evidence,
    write_evidence_file,
    write_json_evidence,
)
from .github_backend import GhCliBackend
from .reviewer import build_rule_review_gates, discover_issue
from .security import maintainer_trust_block_reason, require_ok, run_command
from .workspace import (
    changed_paths,
    git_diff,
    infer_test_commands,
    run_test_commands,
    scan_diff_gate,
)


def _build_auto_issue_fix_model_client(config: AutoIssueFixConfig, workspace_root: Path | None = None):
    from repo_harness.cli import _build_model_client
    from repo_harness.workspace import WorkspaceContext

    workspace_root = Path(workspace_root or config.workspace_root or ".").resolve()
    args = Namespace(
        cwd=str(workspace_root),
        provider=config.provider or "openai",
        _provider_explicit=bool(config.provider),
        model=config.model,
        _model_explicit=config.model is not None,
        base_url=config.base_url,
        _base_url_explicit=config.base_url is not None,
        host=config.host,
        config=None,
        temperature=config.temperature,
        top_p=config.top_p,
        ollama_timeout=config.ollama_timeout,
        openai_timeout=config.openai_timeout,
        max_steps=None,
        _max_steps_explicit=False,
        max_new_tokens=None,
        _max_new_tokens_explicit=False,
        sandbox=None,
        sandbox_backend=None,
    )
    runtime_config = resolve_runtime_config(args, WorkspaceContext.build(workspace_root))
    return _build_model_client(args, runtime_config=runtime_config)


def run_repoharness_fix_turn(
    config: AutoIssueFixConfig,
    issue: AutoIssueFixIssue,
    clone_dir: Path,
    model_client=None,
    workspace_root: Path | None = None,
) -> str:
    from repo_harness.config import sandbox_config_for_directory
    from repo_harness.runtime import RepoHarness
    from repo_harness.session_store import SessionStore
    from repo_harness.workspace import WorkspaceContext

    model = model_client or _build_auto_issue_fix_model_client(config, workspace_root or Path(config.workspace_root or "."))
    session_store = SessionStore(str(clone_dir / ".repo-harness" / "sessions"))
    # The clone's own .repo-harness.toml governs its sandbox. Without this the
    # agent fell back to SandboxConfig() -- mode "off" -- so a repository that
    # declared read_only had every shell command run unsandboxed here, while
    # the same declaration was honoured through the CLI.
    agent = RepoHarness(
        model_client=model,
        workspace=WorkspaceContext.build(clone_dir),
        session_store=session_store,
        approval_policy="auto",
        max_steps=config.max_steps,
        max_new_tokens=config.max_new_tokens,
        read_only=False,
        sandbox_config=sandbox_config_for_directory(clone_dir),
    )
    prompt = f"""You are running inside RepoHarness Auto Issue Fix.

Repository: {issue.repo}
Issue: #{issue.number} {issue.title}
Issue URL: {issue.url}

Issue body:
{issue.body}

Task:
1. Read README, contribution/test configuration, and the relevant source files.
2. Make the smallest useful fix for this issue.
3. Keep changes scoped and avoid unrelated formatting.
4. Run or explain the relevant validation command if available.
5. Finish with a concise summary.
"""
    return agent.ask(prompt)


def maybe_confirm_review_gate(config: AutoIssueFixConfig, stage: str, evidence_dir: Path) -> bool:
    if config.mode != "review-gated":
        return True
    checkpoint = {
        "stage": f"awaiting_human_confirmation:{stage}",
        "mode": config.mode,
        "next_action": f"confirm before {stage}",
    }
    write_json_evidence(evidence_dir, "checkpoint.json", checkpoint, include_local_paths=config.include_local_paths)
    if not sys.stdin.isatty():
        return False
    answer = input(f"Auto Issue Fix review-gated checkpoint before {stage}. Continue? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def run_live_auto_issue_fix(config: AutoIssueFixConfig, model_client=None, gh_backend=None) -> AutoIssueFixRunRecord:
    config.validate()
    workspace_root = Path(config.workspace_root or ".").resolve()
    run_id = default_run_id()
    evidence_dir = Path(config.evidence_dir).resolve() if config.evidence_dir else default_evidence_dir(workspace_root, run_id)
    workdir = Path(config.workdir).resolve() if config.workdir else default_workdir(workspace_root, run_id)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    backend = gh_backend or GhCliBackend()
    context = LiveRunContext(config, run_id, workspace_root, evidence_dir, workdir)

    try:
        context.stage = "issue"
        issue = discover_issue(config, backend, evidence_dir) if config.discover else backend.issue_view(config.repo, int(config.issue or 0))
        context.issue = issue
        write_json_evidence(evidence_dir, "issue.json", issue.to_dict(), include_local_paths=config.include_local_paths)

        if not config.maintainer_access_confirmed:
            context.fallback_reason = (
                "maintainer access was not confirmed; Auto Issue Fix generated local evidence "
                "but will not clone, run model tools, commit, push, or create a draft PR for an unknown third-party repository"
            )
            context.stage = "maintainer-access-blocked"
            context.review_gates.append(
                AutoIssueFixReviewGate(
                    stage="pr-readiness",
                    title="PR Readiness Review",
                    verdict="block",
                    summary="maintainer access was not confirmed",
                    required_action="rerun with --confirm-maintainer-access only for repositories you maintain or are explicitly authorized to change",
                )
            )
            return _finalize_live_record(context, status="blocked", summary="Auto Issue Fix stopped before clone and PR creation.")

        context.stage = "clone"
        if workdir.exists():
            raise RuntimeError(f"workdir already exists: {workdir}")
        workdir.parent.mkdir(parents=True, exist_ok=True)
        backend.clone(issue.repo, workdir)
        context.branch = f"repo-harness-auto-issue-fix-{issue.number}"
        require_ok(run_command(["git", "checkout", "-b", context.branch], cwd=workdir), "git checkout branch failed")

        test_commands = config.test_commands or infer_test_commands(workdir)
        context.stage = "baseline"
        baseline_tests = run_test_commands(test_commands, workdir, evidence_dir / "baseline-repro.log")
        context.baseline_status = "failed" if any(item["status"] == "failed" for item in baseline_tests) else ("passed" if baseline_tests else "not_run")

        context.stage = "fix"
        fix_output = run_repoharness_fix_turn(
            config,
            issue,
            workdir,
            model_client=model_client,
            workspace_root=workspace_root,
        )
        write_evidence_file(evidence_dir, "fix-run.log", fix_output, include_local_paths=config.include_local_paths)

        context.stage = "test"
        context.tests = run_test_commands(test_commands, workdir, evidence_dir / "test-after-fix.log")
        diff_text = git_diff(workdir)
        write_evidence_file(evidence_dir, "git-diff.patch", diff_text, include_local_paths=config.include_local_paths)
        context.changed_paths = list(changed_paths(workdir))
        diff_block = scan_diff_gate(workdir, tuple(context.changed_paths), diff_text)
        message = config.commit_message or f"fix: address issue {issue.number}"
        pr_title = f"Fix #{issue.number}: {issue.title}"
        trust_record = _record_from_live_context(
            context,
            status="pr_ready",
            summary="Prepared a maintainer-facing draft PR body.",
        )
        public_pr_body = render_evidence_templates(trust_record, include_local_paths=config.include_local_paths)["pr-body.md"]
        trust_block = maintainer_trust_block_reason(
            title=pr_title,
            body=public_pr_body,
            commit_message=message,
            branch=context.branch,
        )
        context.review_gates = list(
            build_rule_review_gates(
                config,
                issue=issue,
                diff_block=diff_block,
                maintainer_trust_block=trust_block,
                tests=context.tests,
                changed=tuple(context.changed_paths),
            )
        )
        block_reason = review_gates_block_reason(tuple(context.review_gates), config.max_review_repairs)
        if block_reason:
            context.fallback_reason = block_reason
            context.stage = "blocked"
            return _finalize_live_record(context, status="blocked", summary="Auto Issue Fix stopped before PR creation.")

        if not maybe_confirm_review_gate(config, "commit", evidence_dir):
            context.stage = "paused"
            return _finalize_live_record(context, status="paused", summary="Auto Issue Fix paused before commit for review-gated confirmation.")

        context.stage = "commit"
        require_ok(run_command(["git", "add", "--", *context.changed_paths], cwd=workdir), "git add failed")
        require_ok(run_command(["git", "commit", "-m", message], cwd=workdir), "git commit failed")
        commit_result = run_command(["git", "rev-parse", "HEAD"], cwd=workdir)
        require_ok(commit_result, "git rev-parse failed")
        context.commit = commit_result.stdout.strip()

        if not maybe_confirm_review_gate(config, "push", evidence_dir):
            context.stage = "paused"
            return _finalize_live_record(context, status="paused", summary="Auto Issue Fix paused before push for review-gated confirmation.")

        context.stage = "push"
        backend.ensure_fork_remote(workdir)
        require_ok(run_command(["git", "push", "-u", "fork", context.branch], cwd=workdir), "git push fork failed")

        if not maybe_confirm_review_gate(config, "pr", evidence_dir):
            context.stage = "paused"
            return _finalize_live_record(context, status="paused", summary="Auto Issue Fix paused before draft PR creation.")

        context.stage = "pr"
        pre_pr_record = _record_from_live_context(context, status="pr_ready", summary="Auto Issue Fix prepared a draft PR body.")
        write_evidence(pre_pr_record, include_local_paths=config.include_local_paths)
        base = backend.default_branch(issue.repo)
        context.pr_url = backend.create_pr(
            issue.repo,
            context.branch,
            pr_title,
            evidence_dir / "pr-body.md",
            base,
        )
        write_evidence_file(evidence_dir, "pr-url.txt", context.pr_url + "\n", include_local_paths=config.include_local_paths)
        context.stage = "completed"
        return _finalize_live_record(context, status="completed", summary="Auto Issue Fix created a draft pull request.")
    except Exception as exc:
        context.fallback_reason = f"{type(exc).__name__}: {exc}"
        context.review_gates = list(
            context.review_gates
            or (
                AutoIssueFixReviewGate(
                    stage="task",
                    title="Task Review",
                    verdict="block",
                    summary=f"{type(exc).__name__}: {exc}",
                    required_action="inspect fallback evidence and rerun after fixing the failure",
                ),
            )
        )
        return _finalize_live_record(context, status="failed", summary="Auto Issue Fix failed and wrote fallback evidence.")


def _finalize_live_record(context: LiveRunContext, status: str, summary: str) -> AutoIssueFixRunRecord:
    record = _record_from_live_context(context, status=status, summary=summary)
    write_evidence(record, include_local_paths=context.config.include_local_paths)
    return record


def _record_from_live_context(context: LiveRunContext, status: str, summary: str) -> AutoIssueFixRunRecord:
    issue = context.issue
    return AutoIssueFixRunRecord(
        run_id=context.run_id,
        mode=context.config.mode,
        repo=issue.repo if issue else (context.config.repo or f"auto-discover:{context.config.source}"),
        issue=issue.number if issue else context.config.issue,
        workspace_path=str(context.workspace_root),
        evidence_dir=str(context.evidence_dir),
        status=status,
        summary=summary,
        tests=context.tests,
        pr_url=context.pr_url,
        fallback_reason=context.fallback_reason,
        selected_issue_url=issue.url if issue else "",
        changed_paths=tuple(context.changed_paths),
        auto_review=context.config.auto_review,
        max_review_repairs=context.config.max_review_repairs,
        review_gates=tuple(context.review_gates),
        resume_from=context.config.resume,
        stage=context.stage,
        branch=context.branch,
        commit=context.commit,
        baseline_status=context.baseline_status,
        workdir=str(context.workdir),
    )


def run_auto_issue_fix(config: AutoIssueFixConfig, model_client=None, gh_backend=None) -> AutoIssueFixRunRecord:
    config.validate()
    if not config.dry_run:
        return run_live_auto_issue_fix(config, model_client=model_client, gh_backend=gh_backend)
    workspace_root = Path(config.workspace_root or ".").resolve()
    run_id = default_run_id()
    evidence_dir = Path(config.evidence_dir).resolve() if config.evidence_dir else default_evidence_dir(workspace_root, run_id)
    issue_url = ""
    if config.repo and config.issue is not None:
        repo_ref = config.repo.rstrip("/")
        issue_url = f"{repo_ref}/issues/{config.issue}" if repo_ref.startswith("http") else f"https://github.com/{repo_ref}/issues/{config.issue}"
    tests = [
        {"command": command, "status": "not_run"}
        for command in config.test_commands
    ]
    record = AutoIssueFixRunRecord(
        run_id=run_id,
        mode=config.mode,
        repo=config.repo or f"auto-discover:{config.source}",
        issue=config.issue,
        workspace_path=str(workspace_root),
        evidence_dir=str(evidence_dir),
        status="planned",
        summary="Auto Issue Fix safe preview created a portable evidence scaffold with automatic review gates.",
        tests=tests,
        selected_issue_url=issue_url,
        auto_review=config.auto_review,
        max_review_repairs=config.max_review_repairs,
        review_gates=build_preview_review_gates(config, "planned"),
        resume_from=config.resume,
    )
    write_evidence(record, include_local_paths=config.include_local_paths)
    return record
