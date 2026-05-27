# RepoHarness Auto Issue Fix 产品方案

## 产品定位

RepoHarness Auto Issue Fix 是和 v3 能力完善同等级的重要版本更新。它把 RepoHarness 从本地 coding-agent runtime 扩展为受治理的 GitHub PR 工作流：从 issue 输入、执行计划、证据生成、自动审查、失败阻断，到修复、验证、push 和 draft PR。

当前阶段是 **真实执行 + dry-run 预演**：`repo-harness auto-issue-fix` 默认进入真实执行，支持 GitHub issue 获取、隔离 clone、分支创建、RepoHarness 修复 turn、测试验证、自动审查、commit、push 和 draft PR 创建；`--dry-run` 保留为无副作用预演。

Auto Issue Fix 的产品目标是负责任地帮助开源社区高效解决清晰、可验证的 issue。它不是批量发 PR 的工具，也不把模型输出直接等同于可合并补丁；它输出的是带证据、可审查、可验证的候选修复。默认推荐使用 `review-gated`，所有模式下的 patch、测试结果和 PR 描述都必须经过人工严格 review 和验证后再提交给上游维护者。

P2 dogfood 应描述为 **Auto Issue Fix assisted run**：RepoHarness 完成了真实仓库里的读取、补丁、测试和证据记录；外层选题、diff 审查、遗漏识别、follow-up prompt 和 PR 发布决策仍由人工监督完成。产品化目标是把这些外围编排沉淀为 RepoHarness 自己的可审计能力。

## 目标用户与模式

主要用户：

- 希望用可重复流程修复小型、可验证 GitHub issue 的开发者。
- 希望收到带证据、低噪声候选补丁的维护者。
- 希望用真实开源贡献展示工程闭环的候选人或学习者。

运行模式共享同一套自动审查门：

- `review-gated` 是默认模式。自动审查通过后，关键节点仍由人确认。
- `draft-auto` 必须显式选择。自动审查通过后可以减少人工暂停，但任何 `block` verdict 都必须停止运行并生成 fallback 证据。

`draft-auto` 不是“模型自由执行模式”。它的产品含义是：自动审查驱动的草稿 PR 模式。

任务来源：

- 用户指定 issue：`--repo <url|owner/name> --issue <number>`。
- 自动筛选 issue：`--discover --source trending|repo --criteria bug,test`。
- REPL 引导：普通 REPL 中输入 `/auto-issue-fix` 会依次询问模式、仓库、issue 编号和可选测试命令；默认进入 `review-gated` 真实执行，用户可选择 `dry-run` 只生成预演证据。仓库留空进入全局 discovery，输入仓库但 issue 留空进入 repo-scoped discovery。

## 当前已落地能力

当前已经实现：

- `repo-harness auto-issue-fix` 子命令。
- REPL `/auto-issue-fix` 入口。
- `--dry-run` 证据生成，不执行真实 clone、push 或 PR 创建。
- 非 dry-run 真实执行：issue 获取、隔离 clone、branch、RepoHarness 修复 turn、测试、diff gate、commit、fork push 和 draft PR。
- 自动 discovery：通过 GitHub 候选仓库和 issue 评分选择可执行目标。
- `review-gated` / `draft-auto` 模式参数与风险提示。
- `--auto-review required` 自动审查门策略。
- `--max-review-repairs` 修复回合上限参数。
- `--resume` 恢复参数预留。
- 标准证据模板生成。
- 自动审查门文件、decision log 和 checkpoint。
- 默认路径普适化：使用 `<workspace>`、`<repo>`、`<evidence_dir>` 等占位符，不暴露本机路径。
- 默认脱敏：API key、GitHub token、cookie、secret-shaped 环境变量等写入报告前会被替换为 `<redacted>`。
- 失败 fallback 语义：安全门失败时生成 fallback 描述，而不是强行创建 PR。

当前尚未实现：插件分发层，以及复杂 merge conflict 的自动处理。

## 自动审查门

所有模式都必须经过自动审查门：

- 任务审查：确认 repo、issue、目标、边界和风险。
- 计划审查：检查执行计划、写入范围、测试策略和失败回退。
- 上下文审查：确认模型已读取 issue、README、贡献指南、测试配置等必要材料。
- Diff 审查：检查是否只改必要文件，是否存在无关格式化、大范围重写或意外生成物。
- 测试审查：检查 baseline、修复后测试、失败日志和测试覆盖是否匹配 issue。
- 安全审查：检查 secret、token、本机路径、危险命令、越权写入和供应链风险。
- 维护者信任审查：检查公开 PR title、body、commit message 和 branch，避免把本地工具链、模型、实验记录、trace 或 evidence 说明发布给上游维护者。
- PR 准备审查：检查 PR body、证据包、变更摘要、测试命令和风险说明。

自动审查 verdict 固定为：

- `pass`：允许进入下一阶段。
- `needs_fix`：允许进入受限修复回合。
- `block`：停止执行，生成 fallback 证据。

## 产品价值

Auto Issue Fix 的价值不是“让模型直接发 PR”，而是把 PR 自动化放进可治理生产线：

- 受控执行：模型动作继续经过 permission gate、tool policy、write scope 和 sandbox。
- 可审计：每次运行输出 `.repo-harness/auto-issue-fix/<run_id>/` 证据目录。
- 可恢复：checkpoint 记录当前状态和下一步动作，后续真实执行模式可从 run id 恢复。
- 可追溯：decision log 和 review 文件记录每个关键判断。
- 可迁移：默认报告不含本机绝对路径，适合分享给维护者、面试官或团队成员。
- 模型无关：工作流支持 OpenAI-compatible Responses API、Chat Completions-compatible、Anthropic-compatible、DeepSeek 和 Ollama；MiMo 等 `/chat/completions` 后端应使用 `chat-completions` provider。
- 诚实自动化：不完整或不安全的运行输出 patch / fallback / 报告，而不是伪装成成功 PR。

## 证据模板

每次 Auto Issue Fix 运行写入 `.repo-harness/auto-issue-fix/<run_id>/`：

- `run-record.md`：完整的人类可读审计记录。
- `run-record.json`：机器可读状态，包括模式、门禁、测试、变更路径和 PR 元数据。
- `pr-body.md`：提交给上游维护者的 PR 描述，默认不包含本地路径。
- `formal-report-summary.md`：面试和作品集讲述版总结。
- `pr-ready-fallback.md`：仅在失败或阻断时生成。
- `issue.json`：GitHub issue 快照。
- `baseline-repro.log`：修复前验证命令输出。
- `fix-run.log`：RepoHarness 修复 turn 输出。
- `test-after-fix.log`：修复后验证命令输出。
- `git-diff.patch`：提交前 diff。
- `pr-url.txt`：成功创建 draft PR 后记录 URL。
- `reviews/review-<stage>.json`：每个自动审查门的结构化结果。
- `reviews/review-<stage>.md`：每个自动审查门的人类可读摘要。
- `decision-log.jsonl`：阶段性决策流水。
- `checkpoint.json`：恢复与排障入口。

默认报告会脱敏 API key、GitHub token、cookie、secret-shaped 环境变量、本地用户名和绝对路径。只有用户显式传入 `--include-local-paths` 时，才允许在证据中保留本地绝对路径。

`pr-body.md` 默认使用维护者友好的六段式模板：`Summary`、`Related Issue`、`What Changed`、`Validation`、`Scope and Risk`、`Maintainer Notes`。工具链、模型、实验、trace、benchmark、dogfood 和本地 evidence 说明只保留在本地审计材料中，不默认进入公开 PR 描述。

## 指标

建议跟踪：

- 候选 issue 接受率。
- baseline 可复现率。
- 自动审查 `pass` / `needs_fix` / `block` 分布。
- 受限修复回合次数。
- diff gate 通过率。
- 测试通过率。
- PR 创建率。
- 维护者响应率 / 合并率。
- secret redaction 漏报数。

## 路线图

当前阶段：完成真实执行模式和 dry-run 预演，包括 CLI、REPL、GitHub backend、隔离 clone、RepoHarness 修复 turn、测试门、自动审查门、draft PR、脱敏、路径普适化和 mocked `gh` 测试。

后续阶段：增强 live GitHub dogfood 覆盖、复杂冲突处理、reviewer 模型化，以及官方 workflow plugin 分发。


## 本轮产品化收口

- RepoHarness 的统一定位是：面向本地仓库的可治理 coding-agent runtime；Auto Issue Fix 是其中一个重要的完整工作流。
- `repo-harness provider probe` / `repo-harness provider setup` / `repo-harness provider doctor` 用于降低模型接入摩擦：probe 默认根据 endpoint 或已知厂商根路径推断 provider，不发送模型请求；setup 只写 API key 环境变量名，doctor 可选执行 smoke request 且不打印 secret。
- 真实执行如果要 commit、push 或创建 draft PR，必须显式使用 `--confirm-maintainer-access`，确认用户维护该仓库或被明确授权。
- 证据分三层：用户先看 `formal-report-summary.md`，维护者只看 `pr-body.md`，审计和排障看 `run-record.md`、JSON、reviews、trace 和日志。
