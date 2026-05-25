# 更新日志草稿

## 待发布：RepoHarness 最终版 v3 能力完善与 Auto PR 框架更新

### Added

- 新增 Auto PR 框架与安全预演模式：`repo-harness auto-pr` 支持 `review-gated` / `draft-auto` 模式、标准证据模板、默认脱敏、路径普适化、自动审查门和失败 fallback 语义。
- 新增 REPL `/auto-pr` 入口；未提供仓库和 issue 时生成自动发现规划证据。
- Auto PR 标准证据文件固定为 `run-record.md`、`pr-body.md`、`formal-report-summary.md`、`run-record.json`，失败或阻断时生成 `pr-ready-fallback.md`。
- Auto PR 自动审查文件固定为 `reviews/review-<stage>.json`、`reviews/review-<stage>.md`、`decision-log.jsonl` 和 `checkpoint.json`。
- Provider 配置支持全局 config、项目 `.repo-harness.toml`、项目 `.env`、环境变量和 CLI 显式参数的固定优先级。
- DeepSeek 成为一等 provider，走 Anthropic-compatible client。
- Runtime 覆盖 core executor、permission、tool policy、context usage、session events、report/trace metadata。
- Skills 支持 frontmatter YAML list、allowed tools gate、prompt refresh、fork/model override 和 events。
- Workers 支持后台生命周期、continue、stop、shutdown、running send guard、notifications、artifacts 和 write scope。
- TUI 使用真实 Textual app 路径；不可用时只提供明确 fallback。
- `RunEvidence` 支持 public CLI scripted task，验证 changed file、report、trace、session events 和 state dir。
- Business dogfood 默认 fake/scripted provider，覆盖 `order_pricing_bugfix`、`release_readiness_review`、`incident_resume_fix`。

### Changed

- Auto PR 当前边界明确为框架与安全预演模式，不执行真实 issue discovery、clone/fix/test/push/PR；真实执行模式和插件分发层仍在路线图中。
- `review-gated` 和 `draft-auto` 都必须经过自动审查门；`draft-auto` 不能关闭自动审查。
- 文档体系改为当前说明中文化，用户文档提供操作级指南。
- README、getting-started、architecture、review-pack 和 maintainer-prep 与当前实现同步。
- 长期记忆继续固定为 Review Queue 治理，不允许 skills、workers、evidence 或 Auto PR 直接写 durable topics。
- Memory Pack v1 与文档同步门禁继续保留；`safe-transfer` 只导出 accepted durable memory。
- `/memory self_iteration` 是只读透明入口，不触发 compaction，不会自动写 durable topics；相关审计字段包括 `episodic_compactions`、`self_iteration_review_queued`、`self_iteration_rejections`。
- 当前记忆路线明确为 Memory Self-Iteration v1，不做 Topic Configuration；Semantic Retrieval、embedding 和 vector DB 不作为默认路线。
- 记忆系统继续以可迁移、可审核、可解释为核心，常用入口包括 `/memory review`、`/memory_explain`、`durable_review_queued` 和 `.repo-harness/memory/review-queue.jsonl`。

### Verification

- `uv run pytest tests -q --basetemp C:\tmp\rh-test`
- `uv run ruff check .`
- `git diff --check`
- `uv run --extra tui pytest tests/test_tui.py -q`
