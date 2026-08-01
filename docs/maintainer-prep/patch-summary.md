# 修改摘要记录

## 2026-07-31：v6 / v7 修改摘要（God Object 解体、Builder 提取、Sandbox 加固、测试质量门禁）

### v6：深度审计、God Object 解体推进与安全加固

- `core/prompt_builder.py`、`core/checkpoint_builder.py` 提取为独立纯计算模块，`RepoHarness` 保留瘦转发器。
- `auto_issue_fix` sandbox hardening：read_only 直接阻止 `run_shell`、关闭 .env 覆盖与 fail-open 回退（见 ADR-007）。
- `memory.py`（1,266 行）、`context_manager.py`（668 行）完成深入审计并修复若干缺陷。
- ruff 错误数从 198 降为 0（规则集在 `pyproject.toml` 显式声明并锁版本）。

### v7：Builder 提取收尾、Sandbox 加固与测试质量门禁

- 新增 `core/secret_sanitizer.py`，脱敏逻辑从 `RepoHarness` 提取为独立纯函数模块，配套隔离单测。
- Sandbox hardening 跨 `auto_issue_fix` / `cli` / `tool_policy` / `workspace` / `context_manager` 落实。
- 测试质量门禁：收紧 5 处弱测试（Skills 占位、重复断言、truthy glob、else-True、F841 死代码）；新增 2 类用户场景测试（中断恢复、模型错误可见性）。
- `test_auto_issue_fix_live_runner.py` 从 import smoke 改为离线真驱动 `run_live_auto_issue_fix`。
- 验证：`509 passed, 1 skipped`、`ruff 0 error`。详见 `changelog-draft.md`。

## 2026-05-25：Auto Issue Fix v2 真实执行更新

本次补充新增 `chat-completions` provider，让 MiMo 等 `/chat/completions` 兼容后端可以正式驱动 RepoHarness；`openai` provider 继续代表 Responses API，避免协议混用。

### 背景

Auto Issue Fix 已提升为和 v3 能力完善同等级的重要版本更新。当前阶段新增 `repo-harness auto-issue-fix` 和 REPL `/auto-issue-fix` 的真实执行能力：issue 获取、隔离 clone、RepoHarness 修复 turn、测试、自动审查、commit、push 和 draft PR。`--dry-run` 继续保留为无副作用预演。

Auto Issue Fix 的产品目标收窄为“负责任地帮助开源社区高效解决清晰、可验证的 issue”。默认推荐 `review-gated`；`draft-auto` 不能关闭自动审查，也不替代人的最终 review。所有模式的 patch、测试日志和 PR 描述都必须由人严格复核后再交给上游维护者。

公开 PR 描述与本地证据分离：`pr-body.md` 使用 `Summary`、`Related Issue`、`What Changed`、`Validation`、`Scope and Risk`、`Maintainer Notes` 六段式模板；工具链、模型、实验记录、trace、benchmark、dogfood 和 evidence 说明默认只进入本地 run record / formal report。新增 `maintainer-trust` 审查门和 GitHub blocked / forbidden 错误分类，命中后停止发布并生成 fallback。

### 修改内容

- Auto Issue Fix 专题文档补齐中文产品方案和实现计划。
- README 增加 Auto Issue Fix 真实执行与 dry-run 预演小节，并链接 Auto Issue Fix 产品方案和实现计划。
- getting-started 增加 Auto Issue Fix 操作示例、证据目录、模板文件名和 `--include-local-paths` 风险说明。
- architecture 增加 Auto Issue Fix 编排层说明，明确它复用 CLI/config/runtime/evidence，不绕过 permission gate、tool policy、sandbox 或 RunStore。
- review-pack 增加 Auto Issue Fix 审查重点：自动审查门、维护者信任门、模板、脱敏、真实执行与 dry-run CLI acceptance、默认 mocked `gh`。
- maintainer-prep 增加 Auto Issue Fix 文档同步规则和 GitHub 权限阻断行为准则。

### 当前能力边界

- 已实现：`auto-issue-fix` 子命令、REPL `/auto-issue-fix`、dry-run 预演、真实 issue 获取、discovery、clone/fix/test/push/PR runner、模板生成、自动审查门、维护者信任门、decision log、checkpoint、脱敏、路径普适化、risk notice、失败 fallback 语义。
- 未实现：插件分发层、复杂 merge conflict 自动处理、统一命名调整。

### 记忆治理兼容标记

- Memory Pack v1 与文档同步门继续保留；`safe-transfer` 只导出 accepted durable memory。
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


## 本轮追加摘要

Provider 配置体验新增 Provider Registry、`repo-harness provider probe`、`repo-harness provider setup` 和 `repo-harness provider doctor`，帮助用户从厂商 base URL、model 和 API key 环境变量名推断 provider、生成配置，并在不泄露 secret 的前提下做诊断；probe 默认不发送模型请求。

Auto Issue Fix 增加维护权限确认：真实执行要 clone、运行模型工具、commit、push 或创建 draft PR 时必须显式 `--confirm-maintainer-access`；否则只生成本地证据和 fallback。证据报告增加 metrics summary，并按用户、维护者、审计者三类读者分层。
