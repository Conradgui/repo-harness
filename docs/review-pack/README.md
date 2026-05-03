# Review Pack

## Document Purpose

This document collects review-ready snapshots for maintainers. Each snapshot should explain the project pitch, architecture map, benchmark evidence, and sample run artifacts for a specific review point.

This file is not a permanent one-shot description. When the package name, CLI command, local state directory, or review scope changes, add or update the relevant snapshot instead of silently rewriting historical context.

## Update Rules

- Add a dated snapshot for each major review point.
- Keep historical names and paths inside older snapshots when they describe the state at that time.
- Update this file together with README and maintainer notes when public entrypoints change.

## Review Snapshots

### 2026-05-03: Pre-RepoHarness Rename Snapshot

#### Project pitch

`pico` is a small local coding agent that works inside a repository with constrained tools, resumable sessions, and local audit artifacts.

#### Architecture map

- CLI entrypoints build a configured agent instance.
- The runtime loops through prompt building, model decisions, tool execution, and persistence.
- Runs write task state, traces, and reports under `.pico/runs/`.

#### Benchmark evidence

- Fixed benchmark tasks use deterministic scripted model outputs.
- Each task runs in a fresh fixture copy.
- Verifiers confirm the expected artifact after the agent finishes.

#### Sample run artifact list

- `task_state.json`
- `trace.jsonl`
- `report.json`
