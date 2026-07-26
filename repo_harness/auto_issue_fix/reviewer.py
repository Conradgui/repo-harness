"""Automatic review gates and issue discovery scoring for Auto Issue Fix."""

from __future__ import annotations

from pathlib import Path

from .config import (
    AUTO_REVIEW_STAGES,
    AutoIssueFixConfig,
    AutoIssueFixIssue,
    AutoIssueFixReviewGate,
)
from .evidence import write_evidence_file, write_json_evidence
from .github_backend import GhCliBackend
from .security import normalize_repo


def build_rule_review_gates(
    config: AutoIssueFixConfig,
    *,
    issue: AutoIssueFixIssue | None,
    diff_block: str,
    maintainer_trust_block: str = "",
    tests: list[dict],
    changed: tuple[str, ...],
) -> tuple[AutoIssueFixReviewGate, ...]:
    gates = []
    has_failed_tests = any(item.get("status") == "failed" for item in tests)
    for stage, title, description in AUTO_REVIEW_STAGES:
        verdict = "pass"
        action = "continue"
        summary = description
        if stage == "task" and issue is None:
            verdict = "block"
            action = "select an issue before running Auto Issue Fix"
        elif stage == "diff" and diff_block:
            verdict = "block"
            action = diff_block
            summary = f"{description} {diff_block}"
        elif stage == "tests" and not tests:
            verdict = "block"
            action = "provide --test-command or add a detectable project test command before PR creation"
            summary = f"{description} No validation command was provided or inferred."
        elif stage == "tests" and has_failed_tests:
            verdict = "block"
            action = "fix failing validation commands before PR creation"
            summary = f"{description} One or more validation commands failed."
        elif stage == "pr-readiness" and not changed:
            verdict = "block"
            action = "produce a non-empty diff before PR creation"
            summary = f"{description} No changed files were found."
        gates.append(
            AutoIssueFixReviewGate(
                stage=stage,
                title=title,
                verdict=verdict,
                summary=summary,
                required_action=action,
            )
        )
    gates.append(
        AutoIssueFixReviewGate(
            stage="maintainer-trust",
            title="Maintainer trust review",
            verdict="block" if maintainer_trust_block else "pass",
            summary=maintainer_trust_block
            or "Public PR title, body, commit message, and branch are maintainer-facing.",
            required_action=maintainer_trust_block or "continue",
        )
    )
    return tuple(gates)


def score_issue(issue: AutoIssueFixIssue) -> int:
    text = f"{issue.title}\n{issue.body}".lower()
    labels = {label.lower() for label in issue.labels}
    score = 0
    if labels & {"bug", "type: bug", "test", "tests", "good first issue"}:
        score += 3
    if any(word in text for word in ("reproduce", "repro", "steps", "expected", "actual")):
        score += 3
    if any(word in text for word in ("pytest", "npm test", "go test", "cargo test", "test")):
        score += 2
    if not issue.assignees:
        score += 1
    if any(word in text for word in ("aws", "gcp", "azure", "api key", "credential", "database")):
        score -= 5
    if any(word in text for word in ("refactor", "rewrite", "architecture", "design proposal")):
        score -= 4
    return score


def discover_issue(config: AutoIssueFixConfig, backend: GhCliBackend, evidence_dir: Path) -> AutoIssueFixIssue:
    repos = [normalize_repo(config.repo)] if config.repo else []
    if not repos:
        repos = backend.search_repos(limit=10)
    candidates = []
    for repo in repos[:10]:
        for issue in backend.issue_list(repo, limit=20):
            candidates.append((score_issue(issue), issue))
    candidates.sort(key=lambda item: item[0], reverse=True)
    payload = [{"score": score, **issue.to_dict()} for score, issue in candidates]
    write_json_evidence(evidence_dir, "issue-selection.json", {"candidates": payload})
    lines = ["# Issue Selection", ""]
    for score, issue in candidates[:10]:
        lines.append(f"- score={score} `{issue.repo}#{issue.number}` {issue.title}")
    write_evidence_file(evidence_dir, "issue-selection.md", "\n".join(lines) + "\n")
    if not candidates or candidates[0][0] < 1:
        raise RuntimeError("no suitable issue found during discovery")
    return candidates[0][1]
