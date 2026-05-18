# 更新日志草稿

## 待发布：RepoHarness 最终版 v3 功能对标

### Added

- 新增完整 provider 配置链路：全局 config、项目 `.repo-harness.toml`、项目 `.env`、环境变量和 CLI 显式参数。
- DeepSeek 成为一等 provider，走 Anthropic-compatible client。
- 默认 `max_steps=50`，`max_new_tokens` 按 provider 推断。
- Runtime 补齐 core executor、permission、tool policy、context usage、session events、report/trace metadata。
- Skills 支持 frontmatter YAML list、allowed tools gate、prompt refresh、fork/model override 和 events。
- Workers 支持后台生命周期、continue、stop、shutdown、running send guard、notifications、artifacts 和 write scope。
- TUI 使用真实 Textual app 路径；无依赖时只提供降级 fallback。
- `RunEvidence` 支持 public CLI scripted task，验证 changed file、report、trace、session events 和 state dir。
- Business dogfood 默认 fake/scripted provider，覆盖 `order_pricing_bugfix`、`release_readiness_review`、`incident_resume_fix`。

### Changed

- `approval_policy="ask"` 对同一 risky tool 只触发一次审批。
- 多 tool-call 按顺序执行，partial failure 写入 trace。
- Release evidence 的 business dogfood row 调用真实 `run_dogfood()`。
- 文档体系改为当前说明中文化，用户文档提供操作级指南。

### Governance

长期记忆仍必须经过：

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

`/remember`、`/memory organize`、skills、workers、evidence 和自动整理不会直接写 durable topics。

Memory Pack v1、Review Queue、Explainable Retrieval、Fuzzy Lexical Retrieval 和 Memory Self-Iteration v1 继续保留。相关锚点包括 `/memory review`、`/memory_explain`、`/memory self_iteration`、`safe-transfer`、`durable_review_queued`、`review-queue.jsonl`、`episodic_compactions`、`self_iteration_review_queued`、`self_iteration_rejections`、`score_breakdown` 和 `selected_explanations`。`/memory self_iteration` 是只读入口，不会触发 compaction，也不会自动写 durable topics。

当前边界：不做 Topic Configuration；Semantic Retrieval、embedding 和 vector DB 不作为默认路线。记忆系统继续保持可迁移、可审核、可解释。

### Verification

- `uv run pytest tests -q --basetemp C:\tmp\rh-test`：240 passed, 1 skipped。
- `uv run ruff check .`：passed。
- `git diff --check`：passed，仅有 Windows LF/CRLF 提示。
- `uv run --extra tui pytest tests/test_tui.py -q`：4 passed。
