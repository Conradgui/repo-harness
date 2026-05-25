# 修改摘要记录

## 2026-05-25：Auto PR 框架与安全预演更新

### 背景

Auto PR 已提升为和 v3 能力完善同等级的重要版本更新。当前阶段新增 `repo-harness auto-pr` 和 REPL `/auto-pr` 的框架与安全预演能力，用于生成 PR 自动化证据包、自动审查门、decision log、checkpoint、脱敏报告和路径占位符，不执行真实 GitHub 副作用。

### 修改内容

- Auto PR 专题文档补齐中文产品方案和实现计划。
- README 增加 Auto PR 框架与安全预演小节，并链接 Auto PR 产品方案和实现计划。
- getting-started 增加 Auto PR 操作示例、证据目录、模板文件名和 `--include-local-paths` 风险说明。
- architecture 增加 Auto PR 编排层说明，明确它复用 CLI/config/runtime/evidence，不绕过 permission gate、tool policy、sandbox 或 RunStore。
- review-pack 增加 Auto PR 审查重点：自动审查门、模板、脱敏、安全预演 CLI acceptance、默认 mocked `gh`。
- maintainer-prep 增加 Auto PR 文档同步规则。

### 当前能力边界

- 已实现：`auto-pr` 子命令、REPL `/auto-pr`、dry-run、安全预演、模板生成、自动审查门、decision log、checkpoint、脱敏、路径普适化、risk notice、失败 fallback 语义。
- 未实现：真实 issue discovery、clone/fix/test/push/PR live runner、插件分发层。

### 记忆治理兼容标记

- Memory Pack v1 与文档同步门禁继续保留；`safe-transfer` 只导出 accepted durable memory。
- `/memory review`、`/memory_explain`、`durable_review_queued` 和 `.repo-harness/memory/review-queue.jsonl` 是当前文档必须覆盖的可审核入口。
- `/memory self_iteration` 是只读透明入口，不触发 compaction，不会自动写 durable topics；相关审计字段包括 `episodic_compactions`、`self_iteration_review_queued`、`self_iteration_rejections`。
- 当前记忆路线明确为 Memory Self-Iteration v1，不做 Topic Configuration；Semantic Retrieval、embedding 和 vector DB 不作为默认路线。
- 记忆系统继续以可迁移、可审核、可解释为核心。

## 2026-05-19：最终版 v3 能力完善收尾

### 修改内容

- 完成 RepoHarness 命名收敛：公开 CLI 为 `repo-harness`，模块入口为 `python -m repo_harness`，包名为 `repo_harness`。
- 本地状态目录固定为 `.repo-harness/`。
- Provider 配置支持全局 config、项目 `.repo-harness.toml`、项目 `.env`、环境变量和 CLI 显式参数，优先级固定。
- DeepSeek 成为一等 provider，并覆盖 CLI/config/mock provider 验收。
- Runtime 修复 ask approval 双路径、多 tool-call 顺序和 partial failure trace。
- Skills 支持 YAML list frontmatter，`allowed_tools` 同步刷新 prompt 和 permission gate。
- Workers 支持 factory-created model client、后台 running guard、notifications 和 artifact 汇总。
- `RunEvidence` 增加 public CLI scripted task，验证 changed file、report、trace、session events 和 state dir。
- Release evidence 和 business dogfood row 覆盖真实业务场景。
- TUI normal turn 使用真实 facade/runtime 路径。
- 文档体系改为当前说明中文化，清理过期阶段表述和旧品牌回流风险。

## 历史摘要

- Memory Pack v1 与文档同步门禁：README、getting-started、memory roadmap、patch-summary 和 handoff 必须同时更新。
- 2026-05-18：收敛 plan mode、slash command、permission、ask_user、sandbox required、TUI runtime flow、runtime evidence 和 release gate。
- 2026-05-17：收敛 skills、todo ledger、worker manager、sandbox、runtime control plane、Textual TUI 和 release evidence。
- 2026-05-17：收敛 `.repo-harness.toml`、provider profiles、DeepSeek、tool policy 和 `/remember` Review Queue 入口。
- 2026-05-14：收敛 Memory Self-Iteration v1，自动整理只写 Review Queue candidates。
- 2026-05-14：收敛 Memory Pack、Review Queue 和 Explainable Retrieval v1。
