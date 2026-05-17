# RepoHarness v3 Compat Roadmap

## Summary

RepoHarness v3 compatibility is split into two complete engineering releases. Phase 1 is completed, and Phase 2 is completed as the workflow and UX release. The reference Pico v3 commit is `91a7c17`; the old stable reference tag is `archive-before-repoharness-rename-20260503`.

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

## Boundaries

Do not restore `.pico/`, `.pico.toml`, the `pico` CLI, old Pico screenshots, or old public naming. Do not bypass the Review Queue. Do not let auto-dream or `/remember` write durable memory directly.
