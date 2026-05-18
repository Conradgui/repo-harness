# RepoHarness Review Pack

## 文档目的

本文件为维护者和评审者提供可审查快照。它不替代 README；它说明当前版本应该如何被验证、哪些工件可作为证据、哪些治理边界不能被绕过。

## 2026-05-19：最终版 v3 功能对标快照

本快照覆盖最终版能力：

- provider config：全局 config、项目 config、项目 `.env`、CLI/env/config/default 优先级。
- DeepSeek 一等 provider，走 Anthropic-compatible client。
- core executor、permission、tool policy、sandbox、active tool profile。
- skills frontmatter、prompt section、allowed tools gate。
- worker 后台生命周期、notifications、artifacts、write scope。
- optional Textual TUI，和 REPL 共用 runtime。
- RunEvidence public CLI scripted task。
- business dogfood 三业务场景。
- release evidence scenario contract。

## Review Skeleton

### Project pitch

RepoHarness 是一个本地仓库 coding agent，强调受约束工具、可审计运行工件和 review-gated memory。

### Architecture map

CLI 构建 runtime；runtime 组织 prompt、model output、tool execution、session events、task state、trace 和 report；workers、skills、TUI 和 evidence 共用这条路径。

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
- TUI optional extra 下应有真实 app/pilot smoke；无 Textual 时 fallback 不伪装完整 TUI。
- Skill `allowed_tools` 同时限制 prompt 和实际执行。
- Worker write task 必须有 `write_scope`，Explore worker 只读。

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
uv run --extra tui pytest tests/test_tui.py -q
```

文档同步后额外检查：

```powershell
rg -n "<旧品牌或旧路径关键字>" README.md docs
rg -n "<未完成或过期阶段措辞>" README.md docs
```
