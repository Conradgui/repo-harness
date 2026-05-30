# RepoHarness Review Pack

## 文档目的

本文件为维护者和评审者提供可审查快照。它不替代 README；它说明当前版本应该如何被验证、哪些工件可作为证据、哪些治理边界不能被绕过。

## 2026-05-30：v5 动态上下文预算与代码质量提升

本快照覆盖 v5 版本，包含 v3 能力完善、v4 代码清理与安全加固、以及 v5 动态上下文预算：

- provider config：全局 config、项目 config、项目 `.env`、CLI/env/config/default 优先级。
- Chat Completions-compatible provider：MiMo 等 `/chat/completions` 后端必须走 `chat-completions`，不能误用 `openai` Responses API provider。
- DeepSeek 一等 provider，走 Anthropic-compatible client。
- core executor、permission、tool policy、sandbox、active tool profile。
- skills frontmatter、prompt section、allowed tools gate。
- worker 后台生命周期、notifications、artifacts、write scope。
- 基于 `rich` 的增强 REPL，工具调用卡片、Markdown 渲染、状态栏。
- 动态 context budget：根据模型 context window 自动计算预算（最高 400K 字符）。
- RunEvidence public CLI scripted task。
- business dogfood 三业务场景。
- release evidence scenario contract。
- Auto Issue Fix CLI/REPL 真实执行、dry-run 预演、标准证据包、自动审查门、脱敏、路径普适化、decision log 和 checkpoint。

## Review Skeleton

### Project pitch

RepoHarness 是一个本地仓库 coding agent，强调受约束工具、可审计运行工件和 review-gated memory。

### Architecture map

CLI 构建 runtime；runtime 组织 prompt、model output、tool execution、session events、task state、trace 和 report；workers、skills、REPL 和 evidence 共用这条路径。

### Benchmark evidence

核心证据来自 pytest、mock provider CLI acceptance、RunEvidence public CLI scripted task、business dogfood 三场景和 release evidence scenario rows。

### Sample run artifact list

- `.repo-harness/runs/<run_id>/task_state.json`
- `.repo-harness/runs/<run_id>/trace.jsonl`
- `.repo-harness/runs/<run_id>/report.json`
- `.repo-harness/sessions/<session_id>.events.jsonl`

## 审查重点

- README 和 getting-started 能独立指导用户从安装到运行。
- `.repo-harness/` 是唯一当前状态目录；公开入口是 `repo-harness` 和 `python -m repo_harness`。
- release evidence rows 必须全部通过，并且 artifact path 存在。
- `RunEvidence` 不只跑 help，还要执行 scripted task 并产出 changed file、report、trace、session events。
- business dogfood row 必须调用真实 `run_dogfood()`，并包含以下场景：
  - `order_pricing_bugfix`
  - `release_readiness_review`
  - `incident_resume_fix`
- REPL 基于 `rich` 库，工具调用卡片、Markdown 渲染、状态栏等终端交互增强已验证。
- Skill `allowed_tools` 同时限制 prompt 和实际执行。
- Worker write task 必须有 `write_scope`，Explore worker 只读。
- Auto Issue Fix 当前承诺真实执行与 dry-run 预演：非 dry-run 可执行 issue 获取、隔离 clone、RepoHarness 修复、测试、commit、push 和 draft PR；dry-run 只生成预演证据。
- Auto Issue Fix REPL 应支持无参数引导式流程；普通 REPL 中 `/auto-issue-fix` 默认引导到 `review-gated` 真实执行，非交互环境必须返回 usage 而不是阻塞。
- Auto Issue Fix 两种模式都必须经过自动审查门；`review-gated` 额外保留人工确认，`draft-auto` 不能关闭自动审查。
- Auto Issue Fix 默认推荐 `review-gated`。即使使用 `draft-auto`，最终 patch、测试日志和 PR 描述也必须由人严格 review 和验证后再交给上游维护者。
- Auto Issue Fix 的目标是负责任地帮助开源社区解决清晰、可验证的 issue；不得把它当作批量发布 PR 或绕过维护者判断的工具。
- Auto Issue Fix 标准证据文件固定为 `run-record.md`、`pr-body.md`、`formal-report-summary.md`、`run-record.json`，失败或阻断时生成 `pr-ready-fallback.md`。
- `pr-body.md` 必须使用维护者友好的六段式模板：`Summary`、`Related Issue`、`What Changed`、`Validation`、`Scope and Risk`、`Maintainer Notes`；默认不得包含工具链、模型、实验记录、trace、benchmark、dogfood 或本地 evidence 说明。
- Auto Issue Fix 真实执行证据包括 `issue.json`、`baseline-repro.log`、`fix-run.log`、`test-after-fix.log`、`git-diff.patch`，成功时还包括 `pr-url.txt`。
- Auto Issue Fix 自动审查文件固定为 `reviews/review-<stage>.json`、`reviews/review-<stage>.md`、`decision-log.jsonl` 和 `checkpoint.json`。
- Auto Issue Fix 审查必须覆盖 `maintainer-trust`：公开 PR title、body、commit message 和 branch 中出现工具实验说明、敏感路径、secret 或越权措辞时，应阻断发布并写 fallback。
- Auto Issue Fix 默认测试应使用 mocked `gh`，不得在普通 CI 或单测中访问真实 GitHub、创建 fork 或创建 PR。

## 记忆治理

所有审查都必须保留：

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

`/remember`、`/memory organize`、skills、workers、evidence 和自动整理不得直接写 durable topics。

## 验证命令

```powershell
uv run pytest tests -q --basetemp C:\tmp\rh-test
uv run ruff check .
git diff --check
uv run pytest tests -q
```

文档同步后额外检查：

```powershell
rg -n "<旧品牌或旧路径关键字>" README.md docs
rg -n "<未完成或过期阶段措辞>" README.md docs
```


## 本轮新增审查点

- Provider onboarding：`repo-harness provider probe/setup` 不得写入 API key 值，除非 `probe --write` 显式写入环境变量名；`repo-harness provider doctor` 不得打印 secret，401/404/429 应给出可行动解释。
- Auto Issue Fix live 发布：commit、push、draft PR 前必须有 `--confirm-maintainer-access` 或等价维护权限确认。
- Evidence 分层：`formal-report-summary.md` 给用户先读，`pr-body.md` 给维护者，`run-record.md` / JSON / reviews / trace 用于审计。
- 架构边界：Auto Issue Fix 拆分后的 config、github_backend、security、workspace、reviewer、evidence 模块不得重新互相耦合成单体。
