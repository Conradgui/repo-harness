# 更新日志草稿

## v6：安全加固、稳定性提升、可观测性与多 Agent 编排

### Added

- 新增 `check_dangerous_command()` 危险命令黑名单（`rm -rf /`、`curl | sh`、`shutdown`、`kill -9 -1` 等 20+ 模式），`run_shell` 执行前自动拦截。
- 新增 `/metrics` REPL 命令，展示工具调用统计（成功率、平均耗时）、循环调用检测（连续 4 次相同调用）、热路径分析（最近 20 条中最频繁工具对）、失败率突增告警（≥50% 且 ≥3 次）、session token 消耗估算。
- 新增 `save_metrics_snapshot()` 方法，metrics 快照自动保存到 `.repo-harness/metrics/`（原子写入）。
- `WorkerManager` 新增 `parallel(tasks)` — 并行执行多个 worker，返回结构化结果。
- `WorkerManager` 新增 `pipeline(stages)` — 串行执行，前一个输出通过 `{input}` 传给下一个；stage 失败时后续标记为 skipped。
- `WorkerManager` 新增 `dag(tasks)` — 支持依赖关系的并行执行（拓扑排序 + 批次并行 + 失败阻断下游）。
- `WorkerManager` 新增 `post_message(channel, msg)` / `read_messages(channel, since)` / `clear_messages(channel)` — worker 间消息队列。
- `WorkerManager` 新增 `_update_item()` 原子更新方法，消除 `_get_item` TOCTOU 竞态。
- `runtime.py` 新增 `tool_call_patterns()` — 循环检测、热路径、失败率突增分析。
- `runtime.py` 新增 `session_token_estimate()` + `last_compaction_event()`。
- `runtime.py` 新增 `_sanitize_path()` — 过滤 PATH 中的临时目录。
- `runtime.py` 新增 `_SECRET_REGEX_PATTERNS` — secret 脱敏 regex 后处理（sk-、AKIA、ghp_、Bearer、JWT 等）。
- `SessionStore.save()` 支持 `redact_func` 参数，agent 初始化时自动绑定 `redact_text`。
- `auto_issue_fix/runner.py` 新增 `_sanitize_for_prompt()` — 转义 issue body 中的 `<tool>`/`<final>`/`<plan>` 标签防止 prompt injection。
- `auto_issue_fix/runner.py` 重构为 5 stage 流水线（`_stage_analyze` → `_stage_clone_and_baseline` → `_stage_fix` → `_stage_review` → `_stage_commit_push_pr`）+ 失败重试（默认最多 2 次）。
- `auto_issue_fix/workspace.py` `run_shell_command()` 加危险命令检查 + POSIX 下 `shlex.split` 替代 `shell=True`。
- `evaluator.py` 新增 verifier 命令白名单（`_VERIFIER_ALLOWED_PREFIXES`）。
- `engine.py` 新增 context window 预检：prompt 超限时自动压缩 history 并重建 prompt。
- `memory.py` `_kind_score()` 实现：durable=500, episodic=100（原为永远返回 0）。
- `memory.py` `DurableMemoryStore` 新增 `_write_text_atomic()` 方法。
- `memory.py` `load_index()` / `load_topic_notes()` 新增 `_corruption_warnings` 损坏检测。
- 新增 `tests/test_dangerous_commands.py` — 33 个危险命令测试。
- 新增 `tests/test_worker_orchestration.py` — 23 个编排测试（parallel + pipeline + DAG + 消息队列）。

### Changed

- `SandboxConfig.mode` 默认从 `"off"` 改为 `"best_effort"`；`_resolve_sandbox()` 同步更新。
- bubblewrap 沙箱新增 `--unshare-net` 网络隔离。
- `best_effort` 沙箱回退时输出 stderr 警告（原为静默回退）。
- `search` 工具默认使用 `--fixed-strings` 字面匹配（原为 regex），pattern 长度限制 200 字符。
- `run_shell` 捕获 `subprocess.TimeoutExpired` 返回结构化错误（原为 raw traceback）。
- `tool_read_file` / `tool_patch_file` / `tool_search` 加 `OSError` / `FileNotFoundError` 捕获。
- `tool_patch_file` TOCTOU 修复：执行时重新 `resolve()` 路径。
- `SessionStore.save()` 改为 `tempfile + os.replace` 原子写入（原为直接 `write_text`）。
- `SessionStore.load()` 加 `OSError` / `JSONDecodeError` 捕获（原为直接崩溃）。
- `RunStore.load_task_state()` / `load_report()` 加 `OSError` / `JSONDecodeError` 捕获。
- `DurableMemoryStore._write_index()` / `_write_topic()` 改为原子写入。
- 重复调用守卫从"最近 2 条完全相同"改为"最近 5 条中出现 3 次相同"滑动窗口。
- `runtime.path()` 路径逃逸检查改用 `Path.is_relative_to()`（原为 `os.path.commonpath()`）。
- `context_manager.py` history item 访问改用 `.get()` 带默认值（原为直接 `item["key"]`）。
- `_format_provider_error()` 错误信息统一为英文（原为中英混杂）。
- 所有工具的错误信息包含实际路径（原为 `"path is not a file"` 不含路径）。
- `pyproject.toml` 依赖加版本上限（`<3.0` / `<2026` / `<14.0` / `<4.0`）。
- `skills.py` 通配符导入改为显式导入。
- worker 默认最大 30 步（`DEFAULT_WORKER_MAX_STEPS`），防止僵尸线程。
- 项目级 TOML 配置覆盖 `base_url` / `provider` 时输出 stderr 警告。
- `config.py` `_resolve_sandbox()` 默认从 `"off"` 改为 `"best_effort"`。

### Removed

- 删除 `config.py` 中未使用的 `_int_value()` 函数。
- 删除 `runtime.py` 中未使用的 `note_tool()` 包装方法。
- `compact.py` 中 `CompactManager` 标记为 deprecated（runtime 已直接使用 `compact_history()`）。

### Fixed

- `.env` 加入 `.gitignore`（原未包含，可能导致 API key 泄露）。
- `cli.py` prompt_toolkit 异常加 debug log（原为 `except: pass` 静默吞掉）。
- `tool_policy.py` `_has_fresh_read` 异常加 debug log（原为 `except: return False`）。
- `run_worker` 检查 `task_state.status == "failed"` 检测模型错误（原为仅捕获异常，模型错误返回字符串时状态误判为 "completed"）。

### Verification

- `uv run pytest tests/ -q` — 398 passed, 1 skipped

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
