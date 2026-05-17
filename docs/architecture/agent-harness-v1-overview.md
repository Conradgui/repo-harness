# Agent Harness v1 Overview

## Document Purpose

This document records architecture snapshots for the local Agent Harness. It explains the stable runtime flow, benchmark shape, and artifact semantics at a specific point in the project.

This file should evolve by dated architecture records. If runtime artifact paths, CLI entrypoints, package names, or benchmark semantics change, add a new record or explicitly update the current one with the reason.

## Update Rules

- Add a dated record when the harness architecture or public entrypoints change.
- Do not rewrite older records to hide historical names or paths.
- Keep this overview aligned with maintainer docs and tests that assert review-pack and architecture coverage.

## Architecture Records

### 2026-05-18: v3 Parity Closeout

RepoHarness now routes runtime mode changes, permission decisions, context usage, model requests, parsed model results, tool execution, worker notifications, compaction, and skill activity through session events and enriched trace metadata. `RepoHarness.ask()` remains the public API, while the TUI and REPL use the same runtime state and command handlers.

Closeout additions:

- Plan mode stores active plans under `.repo-harness/plans/` and restricts tools until a non-empty plan artifact exists.
- `/usage`, `/model [name]`, `/history`, `/context`, `/compact`, and `/working-memory` expose runtime state without mutating project configuration.
- Tool permissions, tool policy, worker scope, plan mode, and sandbox denials share one metadata path.
- Runtime reports include `prompt_metadata.context_usage`, `artifact_graph`, `verifier_suggestions`, and `runtime_reminders`.
- `/memory organize` queues Review Queue candidates only.

Durable memory governance remains:

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

### 2026-05-17: v3 Compat Phase 2 Workflow And UX

RepoHarness keeps the existing public `RepoHarness` runtime API while extracting small internal seams for model completion and tool execution through `runtime_control.py`. The REPL, optional TUI, worker manager, todo ledger, sandbox runner, and release evidence runner use the same runtime state and report path.

Phase 2 adds:

- Skills discovery from `skills/<name>/SKILL.md` and `.repo-harness/skills/<name>/SKILL.md`; skills only contribute prompt/control text.
- Session-scoped todos persisted in session JSON and summarized in prompts, trace/report fields, and `todo_changes`.
- Bounded Explore and scoped write workers that inherit tool policy, provider config, secret redaction, and memory governance.
- Sandbox modes `off`, `best_effort`, and `read_only` for `run_shell` execution metadata.
- Optional Textual TUI entry through `--tui`.
- RepoHarness-named release evidence under caller-selected output paths.

The memory boundary is unchanged:

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

### 2026-05-17: v3 Compat Phase 1 Foundation

RepoHarness adds `.repo-harness.toml` configuration, provider profiles for OpenAI, Anthropic, and DeepSeek, and DeepSeek as an Anthropic-compatible provider. Runtime provider metadata records protocol, model, sanitized base URL, attempts, and retry count.

The memory boundary is unchanged:

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

`/remember <text>` only queues candidates. Phase 1 excludes skills, todo ledger, worker manager, sandbox, runtime control plane layering, Textual TUI, and release evidence; those remain Phase 2. Reference v3 commit: `91a7c17`; old stable reference tag: `archive-before-repoharness-rename-20260503`.

### 2026-05-03: RepoHarness Rename Snapshot

#### Summary

RepoHarness is the current public name for the local Agent Harness. Public entrypoints are `repo-harness`, `python -m repo_harness`, the `repo_harness` package, and `.repo-harness/` local state.

#### State directory semantics

RepoHarness stores local sessions, runs, checkpoints, memory, and review queues under `.repo-harness/`. Startup no longer copies state from old brand directories.

#### Agent instruction files

`AGENTS.md` is an optional workspace document. If it is absent, RepoHarness still runs using the built-in runtime rules plus README and project metadata.

### 2026-05-03: Agent Harness v1 Snapshot

#### Summary

Agent Harness v1 evaluates the local agent against deterministic fixture tasks and records reproducible benchmark artifacts.

#### Flow

1. Copy a fixture into a fresh workspace.
2. Build an agent with a scripted model client.
3. Run the task and capture task state, trace, and report artifacts.
4. Verify the expected artifact and summarize the result row.

#### Key artifacts

- task state snapshots describe progress and stop reasons
- trace events capture prompt, tool, and checkpoint activity
- reports summarize the final runtime outcome

