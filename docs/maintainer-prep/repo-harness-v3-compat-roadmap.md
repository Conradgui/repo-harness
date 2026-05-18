# RepoHarness v3 功能对标路线

## Summary

RepoHarness 已完成最终版 v3 功能对标。对标含义是补齐参考仓库新增能力中 RepoHarness 缺失或过浅的部分，同时保留 RepoHarness 自身优势：Review Queue、Memory Pack、Explainable Retrieval、Fuzzy Lexical Retrieval 和 RepoHarness 命名体系。

参考基线：参考仓库 v3 commit `91a7c17`。

历史阶段锚点：Phase 1、Phase 2、Phase 2 Workflow And UX、`repo-harness/v3-compat-phase2`、`archive-before-repoharness-rename-20260503`。这些锚点只用于历史索引；当前用户文档以最终版能力为准。

## 已交付能力

- 配置系统：项目 `.repo-harness.toml`、用户级全局 config、项目 `.env`、CLI/env/config/default 优先级。
- Provider：OpenAI-compatible、Anthropic-compatible、DeepSeek、Ollama。
- Runtime：core executor、permission、tool policy、context usage、session events、report/trace。
- Safety：更严格 shell policy、fresh read before write、重复调用 guard、approval ask once。
- Sandbox：`off`、`best_effort`、`read_only`、`required`。
- Skills：frontmatter、YAML list、allowed tools、prompt refresh、fork/model override。
- Workers：worker manager 支持后台生命周期、continue/stop/shutdown、notifications、artifacts、write scope。
- TUI：可选 Textual TUI app，和 REPL 共用 runtime。
- Evidence：public CLI scripted task、RunEvidence structured payload、release evidence scenario contract。
- Business dogfood：三业务场景，默认 fake/scripted，live opt-in。

## 保留边界

- 不恢复旧状态目录、旧配置文件、旧 CLI 或旧公共命名。
- 不让 `/remember`、`/memory organize`、skills、workers、evidence 或自动整理直接写 durable topics。
- 不把参考仓库的自动记忆写入方式移植到 RepoHarness。
- 不降低 Memory Pack、Review Queue、Explainable Retrieval、Fuzzy Lexical Retrieval 的治理强度。

## 记忆治理

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

Review Queue 是 RepoHarness 的产品边界，不是临时实现差异。

## 后续维护重点

- 保持文档、测试、release evidence 与实现同步。
- 任何 public CLI、provider、sandbox、skills、workers、TUI 或 memory 行为变化，都必须更新 README、getting-started、architecture、review-pack 和本目录维护者文档。
- 文档更新使用独立 `docs:` 提交。
