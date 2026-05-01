# Review Pack

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
