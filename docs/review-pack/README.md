# Review Pack

## Document Purpose

This document collects review-ready snapshots for maintainers. Each snapshot should explain the project pitch, architecture map, benchmark evidence, and sample run artifacts for a specific review point.

This file is not a permanent one-shot description. When the package name, CLI command, local state directory, or review scope changes, add or update the relevant snapshot instead of silently rewriting historical context.

## Update Rules

- Add a dated snapshot for each major review point.
- Keep historical names and paths inside older snapshots when they describe the state at that time.
- Update this file together with README and maintainer notes when public entrypoints change.

## Review Snapshots

### 2026-05-18: v3 Parity Closeout

This snapshot covers the closeout layer: plan mode, slash command parity, unified permission decisions, ask-user prompts, full skill metadata, worker lifecycle notifications, required sandbox mode, TUI runtime flow, review-gated memory organization, runtime evidence, and a 50-scenario release gate.

Review points:

- `/memory organize` and automatic organization only write Review Queue candidates.
- Plan mode can write only the active `.repo-harness/plans/` artifact.
- `/model <name>` changes only the current runtime and does not write `.repo-harness.toml`.
- The release gate reads runtime reports, traces, and session events instead of marking scenarios passed statically.

Durable memory governance remains:

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

### 2026-05-17: v3 Compat Phase 2 Workflow And UX

This review snapshot covers the complete Phase 2 workflow layer: skills, todo ledger, bounded workers, sandbox runner, runtime control plane extraction, optional Textual TUI, and release evidence scenario gate.

Review points:

- `/skills` and `/skill <name> [args]` are RepoHarness-named skill entrypoints and do not write durable memory.
- Todo changes persist in session JSON and appear in prompt/report metadata.
- Workers inherit Phase 1 provider config, tool policy, secret redaction, and memory governance; write workers are scope-limited.
- Sandbox failures enter the same tool metadata, trace, and report flow as normal tool failures.
- The TUI is optional and uses the same runtime, not a separate behavior path.
- Release evidence uses RepoHarness paths such as `release/v3-compat-phase2/` or `docs/review-pack/phase2/`.

Durable memory governance remains:

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

### 2026-05-17: v3 Compat Phase 1 Foundation

This review snapshot covers `.repo-harness.toml`, OpenAI / Anthropic / DeepSeek provider profiles, DeepSeek through the Anthropic-compatible protocol, provider reliability metadata, lightweight tool policy, and `/remember <text>`.

Durable memory governance remains:

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

Phase 1 is complete foundation work. Phase 2 owns skills, todo ledger, worker manager, sandbox, runtime control plane layering, Textual TUI, and release evidence. Reference v3 commit: `91a7c17`; old stable reference tag: `archive-before-repoharness-rename-20260503`.

### 2026-05-03: RepoHarness Rename Snapshot

#### Project pitch

`RepoHarness` is a local repository harness that works inside a repository with constrained tools, resumable sessions, and local audit artifacts.

#### Architecture map

- CLI entrypoints build a configured agent instance.
- The runtime loops through prompt building, model decisions, tool execution, and persistence.
- Runs write task state, traces, and reports under `.repo-harness/runs/`.

#### Benchmark evidence

- Fixed benchmark tasks use deterministic scripted model outputs.
- Each task runs in a fresh fixture copy.
- Verifiers confirm the expected artifact after the agent finishes.

#### Sample run artifact list

- `task_state.json`
- `trace.jsonl`
- `report.json`

