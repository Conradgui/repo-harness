# Review Pack

Snapshot note: this review pack is a maintainer-facing snapshot for the current pre-RepoHarness-rename codebase. If the package name, CLI command, or local state directory changes, update this file in the same commit as the public documentation.

## Project pitch

`pico` is a small local coding agent that works inside a repository with constrained tools, resumable sessions, and local audit artifacts.

## Architecture map

- CLI entrypoints build a configured agent instance.
- The runtime loops through prompt building, model decisions, tool execution, and persistence.
- Runs write task state, traces, and reports under `.pico/runs/`.

## Benchmark evidence

- Fixed benchmark tasks use deterministic scripted model outputs.
- Each task runs in a fresh fixture copy.
- Verifiers confirm the expected artifact after the agent finishes.

## Sample run artifact list

- `task_state.json`
- `trace.jsonl`
- `report.json`
