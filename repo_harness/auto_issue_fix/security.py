"""Security, redaction, and maintainer trust helpers for Auto Issue Fix."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .config import (
    GITHUB_BLOCKED_ERROR_PATTERNS,
    PUBLIC_PR_BODY_FORBIDDEN_TERMS,
    SECRET_PATTERNS,
    AutoIssueFixIssue,
    CommandResult,
)

WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"\b[A-Za-z]:\\[^\s`'\"<>]+")
POSIX_ABSOLUTE_PATH_RE = re.compile(r"(?<![:\w])/(?:Users|home|tmp|var|private|mnt|workspace|repo|opt)[^\s`'\"<>]*")


def redact_text(text: str) -> str:
    redacted = str(text)
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("<redacted>", redacted)
    return redacted


def classify_github_error(text: str) -> str:
    lowered = str(text or "").lower()
    if any(pattern in lowered for pattern in GITHUB_BLOCKED_ERROR_PATTERNS):
        return "blocked_or_forbidden"
    return ""


def _contains_public_forbidden_term(text: str, term: str) -> bool:
    if " " in term or "-" in term:
        return term.lower() in text.lower()
    return re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE) is not None


def maintainer_trust_block_reason(*, title: str, body: str, commit_message: str, branch: str) -> str:
    fields = {
        "title": title,
        "body": body,
        "commit message": commit_message,
        "branch": branch,
    }
    for field_name, value in fields.items():
        # Product naming will be revisited in a later rename pass. For now, keep
        # the existing internal branch prefix from blocking otherwise clean PRs.
        if field_name == "branch" and re.fullmatch(r"repo-harness-auto-issue-fix-\d+", str(value or "")):
            continue
        if redact_text(str(value or "")) != str(value or ""):
            return f"maintainer trust gate blocked public {field_name} secret-shaped content"
        if WINDOWS_ABSOLUTE_PATH_RE.search(str(value or "")) or POSIX_ABSOLUTE_PATH_RE.search(str(value or "")):
            return f"maintainer trust gate blocked public {field_name} local path"
        for term in PUBLIC_PR_BODY_FORBIDDEN_TERMS:
            if _contains_public_forbidden_term(str(value or ""), term):
                return f"maintainer trust gate blocked public {field_name} term: {term}"
    return ""


def normalize_repo(repo: str) -> str:
    value = str(repo or "").strip().removesuffix(".git").rstrip("/")
    if value.startswith("https://github.com/"):
        value = value[len("https://github.com/") :]
    if value.startswith("http://github.com/"):
        value = value[len("http://github.com/") :]
    if value.startswith("git@github.com:"):
        value = value[len("git@github.com:") :]
    return value


def run_command(args, cwd: Path | str | None = None, timeout: int = 300) -> CommandResult:
    cwd_text = str(Path(cwd).resolve()) if cwd else ""
    completed = subprocess.run(
        [str(item) for item in args],
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return CommandResult(
        args=tuple(str(item) for item in args),
        cwd=cwd_text,
        returncode=int(completed.returncode),
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )


def require_ok(result: CommandResult, message: str) -> None:
    if result.ok:
        return
    command = " ".join(result.args)
    classification = classify_github_error(result.combined())
    if classification:
        raise RuntimeError(
            f"{message}: GitHub returned {classification}. "
            "Stop without retrying or bypassing; write fallback evidence instead.\n"
            f"{command}\n{result.combined()}"
        )
    raise RuntimeError(f"{message}: {command}\n{result.combined()}")


def issue_from_gh_payload(repo: str, payload: dict) -> AutoIssueFixIssue:
    labels = tuple(str(item.get("name", item)) for item in payload.get("labels", ()) if item)
    assignees = tuple(str(item.get("login", item)) for item in payload.get("assignees", ()) if item)
    return AutoIssueFixIssue(
        repo=normalize_repo(repo),
        number=int(payload.get("number") or 0),
        title=str(payload.get("title") or ""),
        body=str(payload.get("body") or ""),
        url=str(payload.get("url") or ""),
        labels=labels,
        state=str(payload.get("state") or "open"),
        assignees=assignees,
    )
