# Agent Harness v1 Overview

## Document Purpose

This document records architecture snapshots for the local Agent Harness. It explains the stable runtime flow, benchmark shape, and artifact semantics at a specific point in the project.

This file should evolve by dated architecture records. If runtime artifact paths, CLI entrypoints, package names, or benchmark semantics change, add a new record or explicitly update the current one with the reason.

## Update Rules

- Add a dated record when the harness architecture or public entrypoints change.
- Do not rewrite older records to hide historical names or paths.
- Keep this overview aligned with maintainer docs and tests that assert review-pack and architecture coverage.

## Architecture Records

### 2026-05-03: RepoHarness Rename Snapshot

#### Summary

RepoHarness is the current public name for the local Agent Harness. Public entrypoints are `repo-harness`, `python -m repo_harness`, the `repo_harness` package, and `.repo-harness/` local state.

#### Migration semantics

On startup, RepoHarness copies missing files from a legacy `.pico/` state directory into `.repo-harness/`. Existing `.repo-harness/` files are not overwritten, and `.pico/` is not deleted.

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

