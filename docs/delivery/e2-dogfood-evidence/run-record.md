# Auto Issue Fix Run Record

## Summary

- Run ID: `auto_issue_fix_20260807-032325_3cc831`
- Mode: `draft-auto`
- Repository: `local/fixture`
- Issue: `#1`
- Status: `completed`
- Workspace: `<workspace>`
- Evidence directory: `<evidence_dir>`
- PR URL: `https://github.com/local/fixture/pull/simulated-repo-harness-auto-issue-fix-1`
- Automatic review: `required`
- Max review repairs: `2`
- Stage: `completed`
- Branch: `repo-harness-auto-issue-fix-1`
- Commit: `8362117882fb2ee672547b48bd8d4a92b808c1fa`
- Baseline: `failed`
- Workdir: `<workdir>`

## Result

Auto Issue Fix created a draft pull request.

## Metrics Summary

- Issue selected: `yes`
- Baseline status: `failed`
- Changed files: `1`
- Test commands: `1`
- Tests passed: `1`
- Tests failed: `0`
- Review verdicts: `pass=8, needs_fix=0, block=0`

## Automatic Review Gates

- `task` Task Review: pass
- `plan` Plan Review: pass
- `context` Context Review: pass
- `diff` Diff Review: pass
- `tests` Test Review: pass
- `security` Security Review: pass
- `pr-readiness` PR Readiness Review: pass
- `maintainer-trust` Maintainer trust review: pass

## Tests

- `python -m pytest test_pricing.py -q`: passed

## Changed Paths

- `pricing.py`
