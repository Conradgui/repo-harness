# RepoHarness Auto PR 产品方案

## 产品定位

RepoHarness Auto PR 是和 v3 能力完善同等级的重要版本更新。它把 RepoHarness 从本地 coding-agent runtime 扩展为受治理的 GitHub PR 工作流：从 issue 输入、执行计划、证据生成、自动审查、失败阻断，到后续真实执行模式中的修复、验证、push 和 draft PR。

当前阶段是**框架与安全预演模式**：`repo-harness auto-pr` 已经能生成标准证据包、执行脱敏、保留路径占位符、输出自动审查门记录，并在非 dry-run live 行为前安全阻断。它不会把尚未执行的 clone、fix、test、push 或 PR 创建伪装成已完成。

P2 dogfood 应描述为 **Auto-PR assisted run**：RepoHarness 完成了真实仓库里的读取、补丁、测试和证据记录；外层选题、diff 审查、遗漏识别、follow-up prompt 和 PR 发布决策仍由人工监督完成。产品化目标是把这些外围编排沉淀为 RepoHarness 自己的可审计能力。

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
- REPL 引导：`/auto-pr` 默认进入 `review-gated` 安全预演；用户可显式输入 `/auto-pr --mode draft-auto`。

## 当前已落地能力

当前已经实现：

- `repo-harness auto-pr` 子命令。
- REPL `/auto-pr` 安全预演入口。
- `--dry-run` 证据生成，不执行真实 clone、push 或 PR 创建。
- `review-gated` / `draft-auto` 模式参数与风险提示。
- `--auto-review required` 自动审查门策略。
- `--max-review-repairs` 修复回合上限参数。
- `--resume` 恢复参数预留。
- 标准证据模板生成。
- 自动审查门文件、decision log 和 checkpoint。
- 默认路径普适化：使用 `<workspace>`、`<repo>`、`<evidence_dir>` 等占位符，不暴露本机路径。
- 默认脱敏：API key、GitHub token、cookie、secret-shaped 环境变量等写入报告前会被替换为 `<redacted>`。
- 失败 fallback 语义：安全门失败时生成 fallback 描述，而不是强行创建 PR。

当前尚未实现：

- 真实 issue discovery。
- live clone / fix / test / push / PR runner。
- 插件分发层。

## 自动审查门

所有模式都必须经过自动审查门：

- 任务审查：确认 repo、issue、目标、边界和风险。
- 计划审查：检查执行计划、写入范围、测试策略和失败回退。
- 上下文审查：确认模型已读取 issue、README、贡献指南、测试配置等必要材料。
- Diff 审查：检查是否只改必要文件，是否存在无关格式化、大范围重写或意外生成物。
- 测试审查：检查 baseline、修复后测试、失败日志和测试覆盖是否匹配 issue。
- 安全审查：检查 secret、token、本机路径、危险命令、越权写入和供应链风险。
- PR 准备审查：检查 PR body、证据包、变更摘要、测试命令和风险说明。

自动审查 verdict 固定为：

- `pass`：允许进入下一阶段。
- `needs_fix`：允许进入受限修复回合。
- `block`：停止执行，生成 fallback 证据。

## 产品价值

Auto PR 的价值不是“让模型直接发 PR”，而是把 PR 自动化放进可治理生产线：

- 受控执行：模型动作继续经过 permission gate、tool policy、write scope 和 sandbox。
- 可审计：每次运行输出 `.repo-harness/auto-pr/<run_id>/` 证据目录。
- 可恢复：checkpoint 记录当前状态和下一步动作，后续真实执行模式可从 run id 恢复。
- 可追溯：decision log 和 review 文件记录每个关键判断。
- 可迁移：默认报告不含本机绝对路径，适合分享给维护者、面试官或团队成员。
- 模型无关：工作流应支持 OpenAI-compatible、Anthropic-compatible、DeepSeek、Ollama，以及后续 Chat Completions-compatible provider。
- 诚实自动化：不完整或不安全的运行输出 patch / fallback / 报告，而不是伪装成成功 PR。

## 证据模板

每次 Auto PR 运行写入 `.repo-harness/auto-pr/<run_id>/`：

- `run-record.md`：完整的人类可读审计记录。
- `run-record.json`：机器可读状态，包括模式、门禁、测试、变更路径和 PR 元数据。
- `pr-body.md`：提交给上游维护者的 PR 描述，默认不包含本地路径。
- `formal-report-summary.md`：面试和作品集讲述版总结。
- `pr-ready-fallback.md`：仅在失败或阻断时生成。
- `reviews/review-<stage>.json`：每个自动审查门的结构化结果。
- `reviews/review-<stage>.md`：每个自动审查门的人类可读摘要。
- `decision-log.jsonl`：阶段性决策流水。
- `checkpoint.json`：恢复与排障入口。

默认报告会脱敏 API key、GitHub token、cookie、secret-shaped 环境变量、本地用户名和绝对路径。只有用户显式传入 `--include-local-paths` 时，才允许在证据中保留本地绝对路径。

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

当前阶段：完成框架与安全预演模式，包括 CLI、REPL、证据模板、自动审查门、脱敏、路径普适化、mocked `gh` 测试。

下一阶段：实现 user-specified issue 的真实执行模式，包括 clone、branch、RepoHarness 修复 turn、测试、diff gate、commit、push 和 draft PR。

后续阶段：实现 discovery-driven issue 选择、评分、fallback，以及官方 workflow plugin 分发。
