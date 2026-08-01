"""GitHub CLI backend and shell command helpers for Auto Issue Fix."""

from __future__ import annotations

import json
from pathlib import Path

from .config import AutoIssueFixIssue
from .security import issue_from_gh_payload, normalize_repo, require_ok, run_command


class GhCliBackend:
    def __init__(self, runner=None):
        self.runner = runner or run_command

    def issue_view(self, repo: str, issue: int) -> AutoIssueFixIssue:
        result = self.runner(
            [
                "gh",
                "issue",
                "view",
                str(issue),
                "--repo",
                normalize_repo(repo),
                "--json",
                "number,title,body,url,labels,state,assignees",
            ]
        )
        require_ok(result, "gh issue view failed")
        payload = json.loads(result.stdout or "{}")
        return issue_from_gh_payload(normalize_repo(repo), payload)

    def issue_list(self, repo: str, limit: int = 20) -> list[AutoIssueFixIssue]:
        result = self.runner(
            [
                "gh",
                "issue",
                "list",
                "--repo",
                normalize_repo(repo),
                "--state",
                "open",
                "--limit",
                str(limit),
                "--json",
                "number,title,body,url,labels,state,assignees",
            ]
        )
        require_ok(result, "gh issue list failed")
        return [issue_from_gh_payload(normalize_repo(repo), item) for item in json.loads(result.stdout or "[]")]

    def search_repos(self, query: str = "topic:python sort:stars-desc", limit: int = 10) -> list[str]:
        result = self.runner(
            ["gh", "search", "repos", query, "--limit", str(limit), "--json", "fullName"]
        )
        require_ok(result, "gh search repos failed")
        return [str(item.get("fullName", "")).strip() for item in json.loads(result.stdout or "[]") if item.get("fullName")]

    def default_branch(self, repo: str) -> str:
        result = self.runner(["gh", "repo", "view", normalize_repo(repo), "--json", "defaultBranchRef"])
        require_ok(result, "gh repo view failed")
        payload = json.loads(result.stdout or "{}")
        return str((payload.get("defaultBranchRef") or {}).get("name") or "main")

    def clone(self, repo: str, destination: Path) -> None:
        result = self.runner(["gh", "repo", "clone", normalize_repo(repo), str(destination)])
        require_ok(result, "gh repo clone failed")

    def ensure_fork_remote(self, cwd: Path) -> None:
        result = self.runner(
            ["gh", "repo", "fork", "--remote", "--remote-name", "fork", "--clone=false"],
            cwd=cwd,
        )
        if result.ok:
            return
        remotes = run_command(["git", "remote"], cwd=cwd)
        if "fork" in remotes.stdout.split():
            return
        require_ok(result, "gh repo fork failed")

    def current_user(self) -> str:
        result = self.runner(["gh", "api", "user", "--jq", ".login"])
        require_ok(result, "gh api user failed")
        return result.stdout.strip()

    def create_pr(self, repo: str, branch: str, title: str, body_file: Path, base: str) -> str:
        user = self.current_user()
        result = self.runner(
            [
                "gh",
                "pr",
                "create",
                "--repo",
                normalize_repo(repo),
                "--head",
                f"{user}:{branch}",
                "--base",
                base,
                "--title",
                title,
                "--body-file",
                str(body_file),
                "--draft",
            ]
        )
        require_ok(result, "gh pr create failed")
        return result.stdout.strip().splitlines()[-1].strip()
