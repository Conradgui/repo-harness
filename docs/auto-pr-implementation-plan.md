# RepoHarness Auto PR 实现计划

## 概要

Auto PR 以 RepoHarness 内置子命令和 REPL 命令落地，同时保留未来拆成 workflow plugin 的边界。当前阶段是框架与安全预演模式：公开 CLI、运行配置、证据模板、路径普适化、脱敏、自动审查门、decision log 和 checkpoint 已形成稳定契约。

真实 issue discovery、live clone、修复、测试、push 和 PR 创建属于下一阶段。实现时必须复用现有 CLI/config/provider/runtime/evidence，不绕过 permission gate、tool policy、sandbox 或 RunStore。

## CLI 与 REPL 设计

命令入口：

```bash
repo-harness auto-pr --repo <url|owner/name> --issue <number> --dry-run
repo-harness auto-pr --discover --source trending --criteria bug,test --dry-run
```

REPL 入口：

```text
/auto-pr
/auto-pr --repo owner/name --issue 123
/auto-pr --repo owner/name --issue 123 --mode draft-auto
```

关键参数：

- `--mode review-gated|draft-auto`：默认 `review-gated`。
- `--dry-run`：只生成证据计划，不执行 clone、push 或 PR 副作用。
- `--auto-review required`：自动审查门策略；当前固定为 required。
- `--max-review-repairs <n>`：`needs_fix` 后允许的受限修复回合数，默认 2。
- `--resume <run_id>`：预留给后续真实执行模式恢复。
- `--evidence-dir <path>`：覆盖默认 `.repo-harness/auto-pr/<run_id>`。
- `--workspace-root <path>`：Auto PR 运行和证据生成的工作区根目录。
- `--test-command <command>`：记录或后续执行的验证命令。
- `--include-local-paths`：显式允许报告中保留本地绝对路径。

当前实现中，非 dry-run live runner 仍处于安全阻断状态：会生成证据和 fallback 语义，但不会执行真实 GitHub 副作用。

## 模块边界

`repo_harness.auto_pr` 当前负责：

- `AutoPrConfig`：归一化用户输入、任务来源、模式、自动审查策略和恢复参数。
- `AutoPrReviewGate`：记录每个审查阶段的 verdict、摘要、修复要求和尝试次数。
- `AutoPrRunRecord`：模板和 JSON 使用的可移植运行状态。
- 证据渲染：`run-record.md`、`run-record.json`、`pr-body.md`、`formal-report-summary.md`、`pr-ready-fallback.md`。
- 自动审查工件：`reviews/review-<stage>.json`、`reviews/review-<stage>.md`、`decision-log.jsonl`、`checkpoint.json`。
- 脱敏工具：处理 token、cookie、key-shaped 文本和本地路径。
- CLI/REPL handler：供 `repo_harness.cli` 分发 `auto-pr` 子命令和 `/auto-pr`。

后续真实执行模式应继续放在这个边界内或其子模块中：

- issue 选择与评分。
- Git workspace 准备。
- RepoHarness 修复 turn 构造。
- 自动审查 reviewer。
- 验证门禁。
- GitHub `gh` backend。
- fallback 工件生成。

## 自动审查门设计

所有模式共享自动审查门：

- `review-gated`：自动审查通过后，关键节点仍由人确认。
- `draft-auto`：自动审查通过后，不要求人类中途暂停；任何 `block` 都必须停止。

审查阶段：

- task
- plan
- context
- diff
- tests
- security
- pr-readiness

verdict 固定为：

- `pass`
- `needs_fix`
- `block`

后续真实执行模式中，reviewer 必须只读运行状态、trace 摘要、diff、测试日志和证据包，不允许写文件或执行修复。`needs_fix` 只能触发受限修复 turn，且修复次数不得超过 `--max-review-repairs`。

## GitHub 策略

默认单元测试和 CI 测试使用 mocked `gh`，原因是：

- 测试必须确定、快速、可重复。
- 默认测试不能依赖真实 GitHub 账号、网络、rate limit 或权限状态。
- 默认测试不能意外创建真实 fork、分支或 PR。

真实 GitHub 覆盖必须显式 opt-in：

```bash
REPO_HARNESS_AUTO_PR_LIVE_GITHUB=1
```

live 测试只能使用 sandbox 仓库，必须创建 draft PR，并记录 PR URL 与清理建议。

## 安全行为

live runner 遇到以下任一失败时必须阻断 push / PR：

- 自动审查 verdict 为 `block`。
- `needs_fix` 超过最大受限修复次数。
- test gate 失败。
- diff gate 失败。
- write-scope gate 失败。
- secret scan 失败。
- GitHub authentication 失败。
- branch / fork setup 失败。

阻断后写入 fallback 工件，不强行提交 PR。

## 测试计划

当前阶段测试覆盖：

- 标准模板文件名，包括 `formal-report-summary.md`。
- 默认路径普适化。
- secret redaction。
- dry-run CLI 证据生成。
- REPL `/auto-pr` 默认安全预演。
- `review-gated` 也生成自动审查门。
- `draft-auto` 不能关闭自动审查。
- `block` verdict 生成 fallback 和 review 工件。
- `--max-review-repairs` 参数校验。

后续真实执行模式应增加：

- mocked `gh` fork / push / PR flow。
- 使用 scripted model output 的 fixture repo 修复流程。
- `review-gated` 暂停 / 恢复行为。
- `draft-auto` 无人工暂停行为，并确保所有自动审查门仍生效。
- `needs_fix` 受限修复回合。
- live GitHub opt-in dogfood。
