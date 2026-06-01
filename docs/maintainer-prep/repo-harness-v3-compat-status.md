# RepoHarness v3 能力完善状态

## Current Status

status: completed

最终版能力完善已经完成并合入 `main`。Auto Issue Fix 真实执行与 dry-run 预演是当前版本的同等级重要更新。本文件记录当前事实，不再按早期阶段拆分待办。

参考基线：参考仓库 v3 commit `91a7c17`。RepoHarness 只参考功能能力，不复制品牌、路径、文案或记忆治理方式。

历史锚点：Phase 1、Phase 2、Phase 2 Workflow And UX、`repo-harness/v3-compat-phase2`、`archive-before-repoharness-rename-20260503`。

## 已完成能力

- Provider 配置系统：CLI、process env、项目 `.env`、项目 `.repo-harness.toml`、全局 `%USERPROFILE%\.repo-harness\config.toml`、默认值按固定优先级合并。
- Provider：OpenAI-compatible Responses API、Chat Completions-compatible、Anthropic-compatible、DeepSeek、Ollama；DeepSeek 是一等 provider，走 Anthropic-compatible client。
- 默认参数：`max_steps=50`，`max_new_tokens` 按 provider 推断。
- Runtime：core executor、permission、tool policy、context usage、session events、runtime reports、trace metadata。
- Tool policy：shell read/search 拦截、fresh read before write、重复工具调用 guard、多 tool-call 顺序和 partial failure trace。
- Permission/profile：plan、readonly、worker、skill、memory organize 等路径统一走 profile gate。
- Skills：bundled/project/local skills、frontmatter、YAML list、allowed tools gate、prompt section、fork/model override、skill events。
- Workers：worker manager 支持后台生命周期、continue/stop/shutdown、running send guard、notifications、artifacts、write scope、Explore readonly。
- Sandbox：`off`、`best_effort`、`read_only`、`required`；sandbox 支持 backend metadata、glob excluded commands 和 fail closed。
- REPL：基于 `rich` 的增强 REPL，工具调用卡片、Markdown 渲染、状态栏、slash 命令补全。
- Evidence：`RunEvidence` public CLI scripted task、隔离 workspace、report、trace、session events、state dir、structured payload。
- Business dogfood：默认 fake/scripted provider，场景为 `order_pricing_bugfix`、`release_readiness_review`、`incident_resume_fix`；live provider 必须显式 opt-in。
- Release smoke：scenario id contract、all passed、artifact path exists。
- Auto Issue Fix：`repo-harness auto-issue-fix`、REPL `/auto-issue-fix`、无参数引导式流程、真实执行、dry-run 预演、标准证据包、自动审查门、维护者信任门、draft PR、decision log、checkpoint、脱敏和路径普适化。默认推荐 `review-gated`，所有模式输出都必须人工严格 review 和验证。

## RepoHarness 保留优势

- Memory Pack：safe-transfer、continue-work、full-recovery。
- Review Queue：durable memory 必须人工 review。
- Explainable Retrieval：`/memory_explain`、score breakdown、selected explanations。
- Fuzzy Lexical Retrieval：克制的词面归一化。
- RepoHarness 品牌与路径：`.repo-harness/`、`repo-harness`、`repo_harness`。

## 记忆治理

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

`/remember`、`/memory organize`、skills、workers、evidence 和自动整理只能写候选，不能直接写 durable topics。

## 最新验证

- `uv run pytest tests -q --basetemp C:\tmp\rh-test`：240 passed, 1 skipped。
- `uv run ruff check .`：passed。
- `git diff --check`：passed，仅有 Windows LF/CRLF 提示。
- `uv run pytest tests -q`：326 passed, 1 skipped。
- `uv run pytest tests/test_memory.py tests/test_safety_invariants.py -q -k "review or organize or durable"`：3 passed, 30 deselected。
