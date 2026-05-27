# 更新日志草稿

## 待发布：RepoHarness 最终版 v3 能力完善与 Auto Issue Fix v2 真实执行

### Added

- 新增 `chat-completions` provider，支持 MiMo 等 `/chat/completions` 兼容后端；`openai` provider 继续代表 Responses API。
- REPL `/auto-issue-fix` 增加引导式入口；普通 REPL 中不带参数会依次询问模式、仓库、issue 编号和可选测试命令，默认 `review-gated` 真实执行；支持三种路径：指定 issue、指定 repo 后自动筛选 issue、仓库留空进入全局 discovery。
- 新增 Auto Issue Fix v2 真实执行：issue 获取、隔离 clone、branch、RepoHarness 修复 turn、测试、diff gate、commit、fork push 和 draft PR。
- 保留 Auto Issue Fix dry-run 预演：`repo-harness auto-issue-fix` 支持 `review-gated` / `draft-auto` 模式、标准证据模板、默认脱敏、路径普适化、自动审查门和失败 fallback 语义。
- Auto Issue Fix 默认推荐 `review-gated`；所有模式输出的 patch、测试日志和 PR 描述都必须经过人工严格 review 和验证。
- 新增维护者信任审查门：公开 PR title、body、commit message 和 branch 中出现工具链、模型、实验记录、trace、benchmark、dogfood 或敏感信息时阻断发布。
- `pr-body.md` 改为维护者友好的六段式模板：`Summary`、`Related Issue`、`What Changed`、`Validation`、`Scope and Risk`、`Maintainer Notes`；本地工具链和证据说明默认只保留在 run record / formal report 中。
- GitHub blocked / forbidden / permission denied / cannot perform action 错误会停止运行，不重试、不绕过，并写入 fallback。
- Auto Issue Fix 标准证据文件固定为 `run-record.md`、`pr-body.md`、`formal-report-summary.md`、`run-record.json`，失败或阻断时生成 `pr-ready-fallback.md`。
- Auto Issue Fix 真实执行日志包括 `issue.json`、`baseline-repro.log`、`fix-run.log`、`test-after-fix.log`、`git-diff.patch` 和成功时的 `pr-url.txt`。
- Auto Issue Fix 自动审查文件固定为 `reviews/review-<stage>.json`、`reviews/review-<stage>.md`、`decision-log.jsonl` 和 `checkpoint.json`。
- Provider 配置支持全局 config、项目 `.repo-harness.toml`、项目 `.env`、环境变量和 CLI 显式参数的固定优先级。
- DeepSeek 成为一等 provider，走 Anthropic-compatible client。
- Runtime 覆盖 core executor、permission、tool policy、context usage、session events、report/trace metadata。
- Skills 支持 frontmatter YAML list、allowed tools gate、prompt refresh、fork/model override 和 events。
- Workers 支持后台生命周期、continue、stop、shutdown、running send guard、notifications、artifacts 和 write scope。
- TUI 使用真实 Textual app 路径；不可用时只提供明确 fallback。
- `RunEvidence` 支持 public CLI scripted task，验证 changed file、report、trace、session events 和 state dir。
- Business dogfood 默认 fake/scripted provider，覆盖 `order_pricing_bugfix`、`release_readiness_review`、`incident_resume_fix`。

### Changed

- Auto Issue Fix 当前边界明确为真实执行 + dry-run 预演；默认 PR 为 draft，不自动 ready-for-review。
- `review-gated` 和 `draft-auto` 都必须经过自动审查门；`draft-auto` 不能关闭自动审查。
- 文档体系改为当前说明中文化，用户文档提供操作级指南。
- README、getting-started、architecture、review-pack 和 maintainer-prep 与当前实现同步。
- 长期记忆继续固定为 Review Queue 治理，不允许 skills、workers、evidence 或 Auto Issue Fix 直接写 durable topics。
- Memory Pack v1 与文档同步门禁继续保留；`safe-transfer` 只导出 accepted durable memory。
- `/memory self_iteration` 是只读透明入口，不触发 compaction，不会自动写 durable topics；相关审计字段包括 `episodic_compactions`、`self_iteration_review_queued`、`self_iteration_rejections`。
- 当前记忆路线明确为 Memory Self-Iteration v1，不做 Topic Configuration；Semantic Retrieval、embedding 和 vector DB 不作为默认路线。
- 记忆系统继续以可迁移、可审核、可解释为核心，常用入口包括 `/memory review`、`/memory_explain`、`durable_review_queued` 和 `.repo-harness/memory/review-queue.jsonl`。

### Verification

- `uv run pytest tests -q --basetemp C:\tmp\rh-test`
- `uv run ruff check .`
- `git diff --check`
- `uv run --extra tui pytest tests/test_tui.py -q`


## 本轮追加

- 新增 Provider Registry、`repo-harness provider probe`、`repo-harness provider setup` 和 `repo-harness provider doctor`，用于根据厂商 endpoint 推断 provider、生成 provider 配置、验证 API key 环境变量和解释常见 provider 错误；probe 的真实请求必须显式开启。
- Auto Issue Fix live 发布新增 `--confirm-maintainer-access` 门禁；未确认维护权限时只生成 fallback evidence，不 clone、不运行模型工具、不 commit、不 push、不创建 draft PR。
- Auto Issue Fix evidence 增加 metrics summary，并明确 `formal-report-summary.md`、`pr-body.md`、`run-record.md` 的分层用途。
- Auto Issue Fix 代码按职责拆分为 config、github backend、安全、workspace、reviewer、evidence 和主入口模块。
