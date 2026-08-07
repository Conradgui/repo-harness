from repo_harness.auto_issue_fix import (
    AutoIssueFixConfig,
    AutoIssueFixIssue,
    AutoIssueFixRunRecord,
    GhCliBackend,
    run_live_auto_issue_fix,
)


def test_auto_issue_fix_live_runner_public_entrypoints_are_importable():
    assert GhCliBackend is not None
    assert run_live_auto_issue_fix is not None
    assert AutoIssueFixConfig is not None
    assert AutoIssueFixIssue is not None
    assert AutoIssueFixRunRecord is not None


class FakeBackend:
    """Offline stand-in for GhCliBackend: never touches the network."""

    def issue_view(self, repo, issue):
        return AutoIssueFixIssue(
            repo=str(repo),
            number=int(issue),
            title="offline issue",
            body="offline body",
            url=f"https://github.com/{repo}/issues/{issue}",
            labels=(),
        )

    def issue_list(self, repo, limit=20):
        return [self.issue_view(repo, 1)]

    def search_repos(self, query="topic:python sort:stars-desc", limit=10):
        return []

    def default_branch(self, repo):
        return "main"


def test_auto_issue_fix_live_runner_blocks_without_maintainer_access(tmp_path):
    fake_backend = FakeBackend()
    cfg = AutoIssueFixConfig(
        repo="owner/name",
        issue=1,
        workspace_root=tmp_path,
        discover=False,
        maintainer_access_confirmed=False,
    )

    rec = run_live_auto_issue_fix(cfg, gh_backend=fake_backend)

    assert isinstance(rec, AutoIssueFixRunRecord)
    assert rec.status == "blocked"
    assert rec.tests == []
    assert rec.changed_paths == ()


def test_auto_issue_fix_blocks_before_any_github_fetch(tmp_path):
    """An unconfirmed run must have zero network side effects: the issue is
    never fetched, because the maintainer-access check precedes it."""
    calls = []

    class RecordingBackend(FakeBackend):
        def issue_view(self, repo, issue):
            calls.append("issue_view")
            return super().issue_view(repo, issue)

        def issue_list(self, repo, limit=20):
            calls.append("issue_list")
            return super().issue_list(repo, limit)

        def search_repos(self, query="", limit=10):
            calls.append("search_repos")
            return super().search_repos(query, limit)

    cfg = AutoIssueFixConfig(
        repo="owner/name",
        issue=1,
        workspace_root=tmp_path,
        discover=False,
        maintainer_access_confirmed=False,
    )

    rec = run_live_auto_issue_fix(cfg, gh_backend=RecordingBackend())

    assert rec.status == "blocked"
    assert calls == [], (
        "maintainer-access block must precede any GitHub fetch; "
        f"backend methods called: {calls}"
    )


def test_auto_issue_fix_rejects_missing_workspace_root(tmp_path):
    missing = tmp_path / "no_such_dir"
    cfg = AutoIssueFixConfig(
        repo="owner/name",
        issue=1,
        workspace_root=missing,
        discover=False,
        maintainer_access_confirmed=True,
    )

    import pytest

    with pytest.raises(ValueError, match="does not exist"):
        run_live_auto_issue_fix(cfg, gh_backend=FakeBackend())


def test_auto_issue_fix_rejects_unimplemented_resume(tmp_path):
    cfg = AutoIssueFixConfig(
        repo="owner/name",
        issue=1,
        workspace_root=tmp_path,
        discover=False,
        maintainer_access_confirmed=True,
        resume="some-checkpoint-id",
    )

    import pytest

    with pytest.raises(ValueError, match="resume is not implemented"):
        run_live_auto_issue_fix(cfg, gh_backend=FakeBackend())
