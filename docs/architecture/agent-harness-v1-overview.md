# RepoHarness 架构概览

## 文档目的

本文记录 RepoHarness 当前架构边界、运行工件和维护规则。历史记录只保留必要事实；当前实现以 `repo-harness`、`repo_harness` 和 `.repo-harness/` 为准。

Agent Harness v1 的核心概念仍然保留：一次任务会生成 task state、trace 和 report，以便复现和审计。

## 当前架构记录：2026-05-19 最终版 v3 能力完善

RepoHarness 的公共 API 仍然是 `RepoHarness.ask()`、`repo-harness` CLI 和 `python -m repo_harness`。REPL、TUI、public CLI scripted evidence、workers 和 release evidence 共用同一套 runtime、permission、tool policy、session events、trace/report 工件。

核心链路：

- CLI 读取显式参数、环境变量、项目 `.env`、项目 `.repo-harness.toml`、全局 `%USERPROFILE%\.repo-harness\config.toml`，并按固定优先级合并。
- Runtime 构建 prompt prefix、workspace context、memory context、skills section、tool list 和 active tool profile。
- Model 输出解析为 final answer、tool calls、ask_user 或 control flow。
- Core tool executor 统一执行 permission gate、tool policy、sandbox、write scope、artifact clipping、trace/report metadata。
- Session event bus 记录 runtime mode、tool decisions、context usage、worker notifications、skill activity、compaction 和 evidence 相关事件。

## Provider 和配置

支持 provider：

- `openai`
- `anthropic`
- `deepseek`
- `ollama`

配置优先级：

```text
CLI 显式参数 > process env / 项目 .env > 项目 .repo-harness.toml > 全局 config > 默认值
```

DeepSeek 是一等 provider，底层走 Anthropic-compatible client。默认 `max_steps=50`，`max_new_tokens` 按 provider 推断。

## Tool / Permission / Sandbox

工具执行统一进入 core executor：

- `approval_policy="ask"` 对同一 risky tool 只触发一次审批。
- shell read/search 被 policy 拦截，鼓励结构化 `read_file` / `search`。
- 既有文件写入要求 fresh read。
- 重复工具调用有 guard。
- 多 tool-call 按顺序执行，partial failure 写入 trace。
- 长 shell 输出会裁剪展示，并把完整输出写入 run artifact。

Sandbox 支持 `off`、`best_effort`、`read_only`、`required`。`required` 在后端不可用时 fail closed；Windows fallback 写入明确 metadata。

## Skills、Workers 和 TUI

Skills 从 `skills/<name>/SKILL.md` 与 `.repo-harness/skills/<name>/SKILL.md` 发现。frontmatter 支持常见 YAML list；`allowed_tools` 会同步刷新 prompt 工具列表和实际 permission gate。

Workers 是 session-scoped 子任务。Explore worker 只读；write worker 必须声明 `write_scope`。Worker 支持后台生命周期、continue、stop、shutdown、running send guard、notifications、artifacts 和 parent report 汇总。

TUI 是可选 Textual 入口，和 REPL 共用 runtime。Slash completion、normal turn、ask_user prompt 和 worker notification 不走独立行为路径。

## Auto PR 编排层

Auto PR 是当前版本和 v3 能力完善同等级的重要更新。`repo-harness auto-pr` 和 REPL `/auto-pr` 复用现有 CLI 分发、配置解析、证据目录和脱敏策略，不绕过 permission gate、tool policy、sandbox 或 RunStore。

当前已实现的是框架与安全预演模式：`AutoPrConfig` 归一化用户意图，`AutoPrReviewGate` 记录自动审查门，`AutoPrRunRecord` 记录可移植状态，模板渲染生成 `run-record.md`、`pr-body.md`、`formal-report-summary.md`、`run-record.json` 和失败时的 `pr-ready-fallback.md`。默认报告使用 `<workspace>`、`<repo>`、`<evidence_dir>` 等占位符，并对 token、cookie、API key 和 secret-shaped 内容做 `<redacted>` 脱敏。

自动审查门是两种模式共享的治理层。`review-gated` 是自动审查通过后继续等待人确认；`draft-auto` 是自动审查通过后减少人工暂停。任一阶段出现 `block` verdict 都必须停止运行并生成 fallback 证据。

每次安全预演会生成 `reviews/review-<stage>.json`、`reviews/review-<stage>.md`、`decision-log.jsonl` 和 `checkpoint.json`。后续 live runner 可以在同一边界内补齐 issue discovery、clone、fix、test、push 和 PR 创建，但这些能力当前不应被写成已完成行为。

## Evidence 和 Release Gate

`RunEvidence` 提供结构化结果对象和 public CLI/scripted provider 验收。public CLI scripted task 会验证：

- changed file
- runtime report
- trace
- session events
- state dir

Business dogfood 默认 fake/scripted provider，场景合同为：

- `order_pricing_bugfix`
- `release_readiness_review`
- `incident_resume_fix`

Live provider 必须显式 opt-in。

## 记忆治理边界

RepoHarness 的 durable memory 必须经人工审核：

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

`/remember`、`/memory organize`、skills、workers、evidence 和 memory self-iteration 只能写 Review Queue candidates，不能直接写 `.repo-harness/memory/topics/*.md`。

Memory Pack、Explainable Retrieval、Fuzzy Lexical Retrieval 是 RepoHarness 的保留优势。
