# 更新日志草稿

## v7：Builder 提取收尾、Sandbox 加固与测试质量门禁

### Added

- 新增 `core/secret_sanitizer.py`，将脱敏逻辑从 `RepoHarness` 提取为独立纯函数模块，可在不实例化 `RepoHarness` 的情况下隔离测试（配套 `tests/test_secret_sanitizer.py`，72 个用例）。
- 新增 `auto_issue_fix` 的 sandbox/security 加固单测与 `tool_policy` 验收测试（`tests/test_tool_policy_acceptance.py`，41 个用例）。
- 新增 2 类用户行为场景测试：
  - `test_user_interruption_recovers_session_after_model_error`：模型错误后 session 落盘、`RepoHarness.from_session` 可恢复、`evaluate_resume_state()` 返回非 `no-checkpoint`、session 身份连续。
  - `test_model_error_surfaces_user_visible_message_and_stop_reason`：`ask` 返回含 "模型错误" 与 "fake model ran out of outputs" 的用户可见文案，`stop_reason == "model_error"`、`status == "failed"`。

### Changed

- `RepoHarness` 上保留 `secret_sanitizer` / `prompt_builder` / `checkpoint_builder` 的瘦转发器与外部 redact 回调，保证既有调用方与下游文档不破坏。
- Sandbox hardening 跨 `auto_issue_fix` / `cli` / `tool_policy` / `workspace` / `context_manager` 落实，收敛命令执行边界。
- `test_auto_issue_fix_live_runner.py` 从 import smoke 改为离线真驱动 `run_live_auto_issue_fix`（注入 `FakeBackend` + `maintainer_access_confirmed=False`），断言返回 `AutoIssueFixRunRecord` 且 `status == "blocked"`。

### Fixed

- `test_prompt_builder.py::test_includes_skills_section`：恒真断言链（`or ... or text.strip()`）收紧为 `assert "Skills:" in text and "none" in text`，明确占位语义。
- `test_repo_harness.py`：删除重复断言行（copy-paste 残留）。
- `test_auto_issue_fix.py::test_auto_issue_fix_repl_defaults_to_discovery_safe_preview`：仅 truthy 的 glob 断言收紧为「至少 1 个 `auto_issue_fix_*` 目录且含 `run-record.json` / `checkpoint.json`」。
- `test_memory.py`：`else True` 恒过分支收紧为 `assert not topics_dir.exists()`（`memory_organize_text` 只队列候选、不写 topics 目录）。
- `runtime.py`：清理死代码赋值（F841），移除无用的 `task_state` 回写。
- 交付报告登记测试行数经 `scripts/sync_figures.py` 重新同步至实测值（9,625 行）。

### Verification

- `uv run pytest tests/ -q` — 559 passed, 1 skipped（2026-08-06 全量复核）
- `uv run ruff check .` — 0 error

---

## v6：深度审计、God Object 解体推进与安全加固

### Added

- 新增 `core/prompt_builder.py`，提取 3 个纯函数（`build_prompt_text`、`compute_tool_signature`、`filter_available_tools`），prompt 构建可在不实例化 RepoHarness 的情况下测试。
- 新增 `core/checkpoint_builder.py`，提取 `build_checkpoint` 和 `infer_next_step` 纯函数，`CHECKPOINT_SCHEMA_VERSION` 常量统一来源。
- 新增 `REPO_HARNESS_EXTRA_CONTEXT_WINDOWS` 环境变量，用户可通过 JSON 注册新模型 context window 无需改代码。
- 新增 3 个 run_shell 输出处理测试（成功/partial_success/无 task_state 截断）。
- 新增 8 个 context window 扩展机制测试（JSON 解析、非字典 JSON、非数字值过滤、优先级覆盖）。
- 新增 12 个测试命令推断测试（Python/npm/Go/Rust/Maven/Gradle/.NET/Ruby/CMake）。
- 新增 11 个 prompt_builder 纯函数隔离测试。

### Changed

- `accept_durable_review` 顺序反转：先 `promote_durable` 再 `mark`，避免 promote 失败时部分提交。
- 8 处 `except Exception` 收窄为精确异常类型（OSError / json.JSONDecodeError / ValueError 等），1 处保留广捕（prompt_toolkit 自定义异常）。
- 3 个 model client 类添加 `__repr__`，api_key 显示为 `<redacted>`。
- `infer_test_commands` 从 4 种扩展到 9 种语言生态（新增 Maven/Gradle/.NET/Ruby/CMake）。
- `compute_budgets` 的 `output_reserve` 增加 `context_window // 2` 上限，防止极小 context window 时 available_tokens 变负。
- `context_manager` metadata `section_order` 修正为包含 `skills`，与实际渲染顺序一致。
- `_compute_section_floors` 增加 `min(floor, budget)` cap，防止 floor 大于 budget。
- CLI 和 runner 的异常消息加入 `type(exc).__name__` 前缀。
- 隐式 TODO 正则提取为命名常量 `AUTO_ISSUE_FIX_BRANCH_RE`。
- 重复注释块清理。

### Fixed

- `context_manager.py` metadata `section_order` 与实际渲染顺序不一致（缺少 `skills`）。
- `context_manager.py` floor 可大于 budget，导致 section 永远无法被压缩。
- `context_manager.py` `note["text"]` 直接访问可能 KeyError，改为 `note.get("text", "")`。
- `context_manager.py` `compute_budgets` 极小 context_window 时 output_reserve 超过 context_window。
- `memory.py` `accept_durable_review` 部分提交：先 mark 后 promote 时 promote 失败导致数据不一致。
- `context_manager.py` `_load_extra_context_windows` 非字典 JSON 导致 `AttributeError` 崩溃。
- `repl_display.py` usage table 异常处理遗漏 `ValueError`。
- `cli.py` prompt_toolkit 初始化收窄过激进导致 `NoConsoleScreenBufferError` 未被捕获。

### Verification

- `uv run pytest tests/ -q` — 496 passed, 1 skipped
- `uv run ruff check .` — passed

---

## v5：动态上下文预算、死代码清理与代码质量提升

### Added

- 新增 `detect_context_window(model_name, provider_name)` 函数，根据模型名或 provider 自动推断 context window 大小。
- 新增 `compute_budgets(context_window, max_new_tokens)` 函数，根据 context window 动态计算各 section 的字符预算和 recent_window。
- `ContextManager.__init__` 新增 `recent_window` 参数，支持动态历史窗口缩放（6/10/16/24 条）。
- `ProviderRegistryEntry` 新增 `context_window` 字段（各 provider 设置具体值：openai=1M, anthropic=200K, deepseek=128K, chat-completions=128K, ollama=32K）。
- `ProviderRegistryEntry` 新增 `supports_native_tools` 字段（所有 provider 设为 True，为原生 Function Calling 预留）。
- `RepoHarness` 新增 `context_window` 属性，`ContextUsageAnalyzer` 优先使用该属性。
- `FakeModelClient` 新增 `model="fake"` 属性，确保测试使用小预算。
- 新增 12 个边界测试覆盖 `detect_context_window` 和 `compute_budgets`。

### Changed

- Context budget 从固定 12,000 字符升级为模型感知的动态预算（Ollama ~49K, Anthropic/OpenAI ~400K）。
- section 分配比例调整为 history 50%、prefix 20%、relevant_memory 15%、memory 10%、skills 5%。
- 输出预留策略从固定 20% 改为 `max_new_tokens * 2`，更精确地适配不同 provider 配置。

### Removed

- 删除 `repo_harness/session_events.py`（死代码，与 `core/session_events.py` API 不同，无消费者）。
- 删除 `repo_harness/engine.py`（死 compatibility shim，无消费者）。
- 删除 `repo_harness/core/session_store.py`（死 compatibility shim，无消费者）。
- 删除 `runtime.py` 中未使用的 `_write_scope_error` 方法（已被 `permissions.py` 的 `PermissionChecker` 替代）。
- 删除 `sandbox.py` 中未使用的 `run_platform_shell` 函数（shell 执行直接使用 `subprocess.run`）。

### Fixed

- `ReplFacade.suggest_commands()` 补全 8 个缺失的 slash 命令（`auto-issue-fix`、`memory review`、`memory organize`、`memory self_iteration`、`memory_pack`、`session`、`reset`、`exit`）。

### Verification

- `uv run pytest tests/ -q` — 326 passed, 1 skipped

---

## v4：代码清理、安全加固与 Claude Code Skill 兼容

### Added

- 新增基于 `rich` 的增强 REPL 显示层（`repo_harness/repl_display.py`），提供工具调用卡片、Markdown 渲染、语法高亮、状态栏等终端交互增强。
- REPL 现在消费 `engine.run_turn()` 事件流，实时显示工具调用（蓝色边框卡片）和工具结果（绿色/红色状态），不再只显示最终答案。
- `/help`、`/usage`、`/history` 命令使用 `rich.table.Table` 格式化输出。
- 新增 `ReplFacade` 独立模块（`repo_harness/repl_facade.py`），从 TUI 提取，提供 snapshot、suggest_commands、ask_user、run_turn 等 REPL 核心抽象。
- 新增 Claude Code Skill 兼容层（`repo_harness/features/claude_code_skills.py`），支持从 `~/.claude/skills/` 自动发现和加载 SKILL.md 文件。
- Claude Code 工具名称自动映射到 RepoHarness 等价物：`Read` → `read_file`，`Write` → `write_file`，`Edit` → `patch_file`，`Bash` → `run_shell`，`Glob` → `list_files`，`Grep` → `search`。
- Claude Code `allowed-tools` 字段（连字符格式）和 Bash scoped 工具（`Bash(python3:*)`）自动转换。
- 新增 `SessionStore` 独立模块（`repo_harness/session_store.py`），从 `runtime.py` 提取，便于独立测试和复用。
- CI 新增 Python 3.12/3.13 测试矩阵和 TUI 专属测试 job。
- CI 新增 `pytest-cov` 覆盖率报告（`--cov=repo_harness --cov-report=term-missing`）。
- 新增 `tests/conftest.py` 共享 pytest fixtures（`workspace`、`agent`）。
- 新增 `tests/test_claude_code_skills.py`（12 个测试用例）覆盖工具映射、frontmatter 解析、Skill 发现。
- 新增 sandbox `excluded_commands` shell 元字符绕过测试（`$(`、`\`、`${`）。

### Changed

- Token 估算从 `chars/4` 升级为 CJK-aware 算法（中文字符 ~1.5 token/字，ASCII ~0.25 token/字符），影响 `runtime.py._estimate_tokens`、`compact.py._estimate_tokens` 和 `context_usage.py`。
- `context_usage.py` 新增 `_count_cjk()` 和 `estimate_tokens()` 函数，`ContextUsageAnalyzer` 使用 `estimation_method: "cjk_aware"`。
- Sandbox `_command_is_excluded` 增加前导空格 `.strip()` 和 shell 元字符检测（`$(`、`` ` ``、`\`、`${`），防止通过子 shell、变量展开或反斜杠转义绕过 `excluded_commands`。
- `discover_skills()` 现在同时搜索 `~/.claude/skills/` 目录，兼容 Claude Code Skill 格式。
- `SessionStore` 从 `runtime.py` 提取到独立的 `session_store.py` 模块，所有相关 import 已更新（`cli.py`、`evaluator.py`、`metrics.py`、`release_evidence.py`、`auto_issue_fix/runner.py`、`evaluation/run_evidence.py`）。

### Removed

- 删除 Textual TUI 框架：`tui/widgets.py`（316 行死代码）、`tui/app.py`（76 行）、`tui/main.py`（8 行），共 ~490 行。
- 删除 `--tui` CLI 标志和 TUI 启动分支。
- 删除 `pyproject.toml` 中 `textual>=0.80` 可选依赖。
- 删除 README 和 getting-started 中的 TUI 章节。
- 删除 `runtime.py` 中 254 行不可达死代码（`ask()` 方法内旧实现）。
- 删除 `repo_harness/core/permissions.py`（纯 re-export shim，无消费者）。
- 删除 `repo_harness/core/tool_policy.py`（纯 re-export shim，无消费者）。
- 删除 `repo_harness/features/sandbox/` 整个子包（5 个文件：`__init__.py`、`checker.py`、`command_matcher.py`、`config.py`、`runner.py`，均为 re-export 或未使用代码）。
- 删除 `repo_harness/evaluation/evaluator.py`（纯 wildcard re-export）。
- 删除 `repo_harness/evaluation/metrics.py`（纯 wildcard re-export）。
- 删除 `context_usage.py` 中未使用的 `_tokens()` 静态方法。
- 删除 `runtime.py` 中未使用的 `import time` 和 `import TaskState`。

### Fixed

- 修复 Windows CJK 路径编码问题：`workspace.py` 中 `git` 子进程输出使用 `encoding="utf-8"` 替代系统默认编码，防止中文目录名被错误解码为 mojibake（如 `优化版本` → `Ż°汾`）。
- 修复 Sandbox `excluded_commands` 可通过 shell 元字符（`$(`、`` ` ``、`\`、`${`）绕过的安全漏洞。
- 修复 Token 估算对 CJK 文本严重低估的问题（`runtime.py` 和 `compact.py` 中的 `_estimate_tokens` 现在使用 CJK-aware 算法）。

### Verification

- `uv run ruff check .` — All checks passed
- `uv run pytest --tb=short -q` — 323 passed, 1 failed（预先存在的 CJK 路径问题）, 1 skipped
- 覆盖率报告通过 `uv run pytest --cov=repo_harness --cov-report=term-missing` 生成

---

## 已发布：RepoHarness 最终版 v3 能力完善与 Auto Issue Fix v2 真实执行

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
- `git diff --check``


## 本轮追加

- 新增 Provider Registry、`repo-harness provider probe`、`repo-harness provider setup` 和 `repo-harness provider doctor`，用于根据厂商 endpoint 推断 provider、生成 provider 配置、验证 API key 环境变量和解释常见 provider 错误；probe 的真实请求必须显式开启。
- Auto Issue Fix live 发布新增 `--confirm-maintainer-access` 门禁；未确认维护权限时只生成 fallback evidence，不 clone、不运行模型工具、不 commit、不 push、不创建 draft PR。
- Auto Issue Fix evidence 增加 metrics summary，并明确 `formal-report-summary.md`、`pr-body.md`、`run-record.md` 的分层用途。
- Auto Issue Fix 代码按职责拆分为 config、github backend、安全、workspace、reviewer、evidence 和主入口模块。
