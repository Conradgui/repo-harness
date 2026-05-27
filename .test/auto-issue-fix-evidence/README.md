# Auto Issue Fix Evidence

This directory stores curated, stable test evidence for the Auto Issue Fix provider and evidence closure release.

Raw `.pytest-temp-*` and `.pytest_cache/` directories are intentionally not committed. They are local pytest workspaces that may contain machine-specific paths, timestamps, generated session ids, and transient runtime artifacts.

## Release Commit

- Repository: `https://github.com/Conradgui/repo-harness.git`
- Branch: `main`
- Released commit: `f524fc5ccd49ae418a8b9327e506485035825d48`
- Evidence recorded on: `2026-05-27`

## Evidence Files

- `pytest-summary.txt`: full test suite result captured before publishing the release commit.
- `quality-summary.txt`: lint, diff check, and repository hygiene checks.
- `scope-summary.md`: high-level behavior covered by the evidence.
