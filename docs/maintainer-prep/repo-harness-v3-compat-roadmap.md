# RepoHarness v3 Compat Roadmap

## Summary

RepoHarness v3 compatibility was delivered as two complete engineering releases plus a parity closeout. Phase 1 is completed, Phase 2 is completed as the workflow and UX release, and the closeout completes the remaining runtime, command, evidence, and governance gaps. The reference Pico v3 commit is `91a7c17`; the old stable reference tag is `archive-before-repoharness-rename-20260503`.

## Phase 1: Foundation Release

Phase 1 adds the foundation layer:

- `.repo-harness.toml` project configuration.
- Provider profiles for OpenAI, Anthropic, and DeepSeek.
- DeepSeek as a first-class provider through the Anthropic-compatible Messages path.
- Default `max_steps = 50` and provider-inferred `max_new_tokens`.
- Provider reliability metadata: protocol, model, sanitized base URL, attempts, and retry count.
- Lightweight tool policy for shell read/search avoidance, fresh reads before existing-file edits, and repeated call guards.
- `/remember <text>` as a Review Queue-only durable memory candidate entrypoint.

Durable memory governance remains:

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

`/remember` and memory self-iteration only queue candidates. They do not write durable topics.

## Phase 2: Workflow And UX Release

Phase 2 completes the workflow and UX layer:

- Skills discovery and `/skills` / `/skill <name> [args]`.
- Session-scoped todo ledger with prompt and report state.
- Bounded worker manager with read-only Explore workers and scoped write workers.
- Sandbox modes `off`, `best_effort`, and `read_only`; sandbox is enforced through the shell runner path.
- Runtime control plane layering through small internal model/tool execution seams.
- Textual TUI optional entry that uses the same runtime.
- Release evidence and scenario gate under RepoHarness-named paths.

Skills, workers, `/remember`, and release evidence do not write durable topics directly.

## v3 Parity Closeout

The closeout completes the remaining parity surface:

- Plan mode through `/plan <topic>`, `/plan-exit`, `/mode`, and `.repo-harness/plans/<slug>-plan.md`.
- Slash command parity for `/usage`, `/model [name]`, `/history`, `/context`, `/compact`, and `/working-memory`.
- Unified permission checker and tool profiles for default, plan, readonly, worker, skill, and memory organize flows.
- `ask_user` tool, session event bus, context usage metadata, manual compaction, runtime artifact graph, verifier suggestions, and runtime reminders.
- Full skill frontmatter, `$ARGUMENTS`, `${REPO_HARNESS_SKILL_DIR}`, fork skills, and skill events.
- Worker send/stop notifications and plan-mode Explore-only enforcement.
- Sandbox mode `required` and backend availability metadata.
- TUI runtime flow with slash suggestions and ask-user prompt support.
- `/memory organize`, which borrows the organization idea but only queues Review Queue candidates.
- 50-scenario release evidence gate that reads runtime reports, traces, and session events.

Memory organize remains review-gated:

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

## Boundaries

Do not restore `.pico/`, `.pico.toml`, the `pico` CLI, old Pico screenshots, or old public naming. Do not bypass the Review Queue. Do not let auto-dream or `/remember` write durable memory directly.
