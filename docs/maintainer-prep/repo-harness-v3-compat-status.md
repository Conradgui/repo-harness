# RepoHarness v3 Compat Status

## Current Status

status: completed

Phase 1 Foundation Release is completed on branch `repo-harness/v3-compat-phase1`.
Phase 2 Workflow And UX Release is completed on branch `repo-harness/v3-compat-phase2`.

Reference Pico v3 commit: `91a7c17`.
Old stable reference tag: `archive-before-repoharness-rename-20260503`.

Allowed status values: `planned`, `in_progress`, `completed`, `blocked`.

## Phase 1 Completed

- `.repo-harness.toml` configuration with CLI > environment > file > default precedence.
- OpenAI, Anthropic, and DeepSeek provider profiles.
- DeepSeek through the Anthropic-compatible protocol.
- Provider reliability metadata with sanitized base URL, attempts, and retry count.
- Lightweight tool policy for run_shell read/search rejection, fresh reads before existing-file edits, and repeated call protection.
- `/remember <text>` queueing durable memory candidates for `/memory review`.

## Phase 2 Completed

- Skills discovery from `skills/<name>/SKILL.md` and `.repo-harness/skills/<name>/SKILL.md`.
- REPL commands `/skills` and `/skill <name> [args]`.
- Session-scoped todo ledger with `todo_add`, `todo_update`, `todo_list`, prompt state, and report state.
- Bounded worker manager with `/agents`, `/subagent explore <task>`, and `/subagent worker --scope <path[,path]> <task>`.
- Sandbox config through `.repo-harness.toml`, `--sandbox`, and `--sandbox-backend`; modes are `off`, `best_effort`, and `read_only`.
- Runtime control plane layering for model completion and tool execution.
- Optional Textual TUI entry through `--tui`.
- Release evidence scenario gate under RepoHarness-named output paths.

Durable memory governance remains:

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

Skills, workers, `/remember`, and release evidence do not directly write `.repo-harness/memory/topics/*.md`.

## Release Fields

- Phase 1 baseline commit: `e1842d6`
- Phase 1 commit: `2487dd5`
- Phase 1 push branch: `repo-harness/v3-compat-phase1`
- Phase 2 commit: final pushed `feat: add v3 compat workflow ux` commit on `repo-harness/v3-compat-phase2`
- Phase 2 push branch: `repo-harness/v3-compat-phase2`

## Verification

- `uv run pytest tests/test_repo_harness.py tests/test_memory.py tests/test_memory_pack.py tests/test_safety_invariants.py -q -k "provider or deepseek or config or tool_policy or repeated or remember or review or memory_pack or docs"`: Phase 1 targeted suite passed.
- `uv run pytest tests/test_repo_harness.py tests/test_safety_invariants.py tests/test_memory.py -q -k "skills or skill or todo or worker or sandbox or tui or scenario or evidence or review"`: 11 passed, 128 deselected.
- `uv run pytest tests/test_tui.py tests/test_skills_acceptance.py tests/test_todo_ledger_acceptance.py tests/test_agent_workers_acceptance.py tests/test_sandbox_runner.py tests/test_run_evidence.py -q`: 10 passed.
- `uv run ruff check .`: passed.
- `git diff --check`: passed with Windows LF/CRLF warnings only.
- `uv run pytest tests -q --basetemp C:\tmp\rh-test`: 194 passed.
