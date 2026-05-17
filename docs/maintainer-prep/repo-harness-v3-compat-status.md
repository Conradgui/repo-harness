# RepoHarness v3 Compat Status

## Current Status

status: completed

Phase 1 is the Foundation Release for v3 compatibility. It is complete when tests pass, the commit is created as `feat: add v3 compat foundation`, and the branch is pushed to `repo-harness/v3-compat-phase1`.

## Completed

- `.repo-harness.toml` configuration with CLI > environment > file > default precedence.
- OpenAI, Anthropic, and DeepSeek provider profiles.
- DeepSeek through the Anthropic-compatible protocol.
- Provider reliability metadata with sanitized base URL, attempts, and retry count.
- Lightweight tool policy for run_shell read/search rejection, fresh reads before existing-file edits, and repeated call protection.
- `/remember <text>` queueing durable memory candidates for `/memory review`.

Durable memory governance remains:

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

## Deferred To Phase 2

Skills, todo ledger, worker manager, sandbox, runtime control plane layering, Textual TUI, and release evidence / scenario gate are Phase 2 work.

Reference Pico v3 commit: `91a7c17`.
Old stable reference tag: `archive-before-repoharness-rename-20260503`.

## Release Fields

- baseline commit: `e1842d6`
- commit: final hash is the `feat: add v3 compat foundation` commit on the pushed branch
- push branch: `repo-harness/v3-compat-phase1`
- allowed status values: `planned`, `in_progress`, `completed`, `blocked`

## Verification

- `uv run pytest tests/test_repo_harness.py tests/test_memory.py tests/test_memory_pack.py tests/test_safety_invariants.py -q -k "provider or deepseek or config or tool_policy or repeated or remember or review or memory_pack or docs"`: 51 passed.
- `uv run ruff check .`: passed.
- `git diff --check`: passed with Windows line-ending warnings only.
- `uv run pytest tests -q --basetemp C:\tmp\rh-test`: 183 passed.
