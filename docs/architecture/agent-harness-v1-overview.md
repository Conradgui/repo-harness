# Agent Harness v1 Overview

## Summary

Agent Harness v1 evaluates the local agent against deterministic fixture tasks and records reproducible benchmark artifacts.

## Flow

1. Copy a fixture into a fresh workspace.
2. Build an agent with a scripted model client.
3. Run the task and capture task state, trace, and report artifacts.
4. Verify the expected artifact and summarize the result row.

## Key artifacts

- task state snapshots describe progress and stop reasons
- trace events capture prompt, tool, and checkpoint activity
- reports summarize the final runtime outcome
