# 修复摘要记录

## 2026-05-19：最终版 v3 功能对标收尾

### 背景

上一轮对标已经完成大部分结构迁移，但仍有配置系统、public CLI evidence、business dogfood、worker lifecycle、skill profile prompt refresh、TUI real app smoke 等收尾缺口。目标是补齐功能能力，同时保持 RepoHarness 的命名体系和记忆治理优势。

### 修复内容

- Provider 配置支持全局 config、项目 `.repo-harness.toml`、项目 `.env`、环境变量和 CLI 显式参数，优先级固定。
- DeepSeek 作为一等 provider 进入 CLI/config/mock provider 验收。
- Runtime 修复 ask approval 双重审批，多 tool-call 顺序与 partial failure trace。
- Skills 支持 YAML list frontmatter，`allowed_tools` 同步刷新 prompt 和 permission gate。
- Workers 支持 factory-created model client、后台 running guard、notifications 和 artifact 汇总。
- `RunEvidence` 新增 public CLI scripted task，验证 changed file、report、trace、session events 和 state dir。
- Release evidence 的 business dogfood row 调用真实三业务场景。
- TUI normal turn 走真实 facade/runtime 路径。
- 文档体系改为当前说明中文化，清理过期阶段表述和旧品牌回流风险。

### 验证结果

- `uv run pytest tests -q --basetemp C:\tmp\rh-test`：240 passed, 1 skipped。
- `uv run ruff check .`：passed。
- `git diff --check`：passed，仅有 Windows LF/CRLF 提示。
- `uv run --extra tui pytest tests/test_tui.py -q`：4 passed。

### 记忆治理

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

任何 skill、worker、evidence、memory organize 或自动整理都不能直接写 durable topics。

记忆系统兼容锚点：`/memory_explain`、`/memory self_iteration`、`safe-transfer`、`.repo-harness/memory/review-queue.jsonl`、`durable-review-queue-v1`、`durable_review_queued`、`episodic_compactions`、`self_iteration_review_queued`、`self_iteration_rejections`、Pending queue、`score_breakdown`、`selected_explanations`。这些字段用于证明可迁移、可审核、可解释。

Memory Self-Iteration v1 当前边界：不做 Topic Configuration；Semantic Retrieval、embedding 和 vector DB 不作为默认路线。

## 历史摘要

- Memory Pack v1 与文档同步门禁：README、getting-started、memory roadmap、patch-summary 和 handoff 必须同时更新。
- 2026-05-18：补齐 plan mode、slash command、permission、ask_user、sandbox required、TUI runtime flow、runtime evidence 和 release gate。
- 2026-05-17：补齐 skills、todo ledger、worker manager、sandbox、runtime control plane、Textual TUI 和 release evidence。
- 2026-05-17：补齐 `.repo-harness.toml`、provider profiles、DeepSeek、tool policy 和 `/remember` Review Queue 入口。
- 2026-05-14：完成 Memory Self-Iteration v1，自动整理只写 Review Queue candidates。
- 2026-05-14：完成 Memory Pack、Review Queue 和 Explainable Retrieval 的 v1 收尾。
