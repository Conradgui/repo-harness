# RepoHarness 架构概览

## 文档目的

本文记录 RepoHarness 当前架构边界、运行工件和维护规则。历史记录只保留必要事实；当前实现以 `repo-harness`、`repo_harness` 和 `.repo-harness/` 为准。

Agent Harness v1 的核心概念仍然保留：一次任务会生成 task state、trace 和 report，以便复现和审计。

## 当前架构记录：2026-06-03 v6 安全加固、稳定性提升、可观测性与多 Agent 编排

RepoHarness 的公共 API 仍然是 `RepoHarness.ask()`、`repo-harness` CLI 和 `python -m repo_harness`。REPL、public CLI scripted evidence、workers 和 release evidence 共用同一套 runtime、permission、tool policy、session events、trace/report 工件。

核心链路：

- CLI 读取显式参数、环境变量、项目 `.env`、项目 `.repo-harness.toml`、全局 `%USERPROFILE%\.repo-harness\config.toml`，并按固定优先级合并。项目级 TOML 覆盖 `base_url` / `provider` 时输出 stderr 警告。
- Runtime 构建 prompt prefix、workspace context、memory context、skills section、tool list 和 active tool profile。
- **Context window 预检**：prompt 超限时自动压缩 history 并重建 prompt，再调用模型。
- Model 输出解析为 final answer、tool calls、ask_user 或 control flow。
- Core tool executor 统一执行 permission gate、tool policy、sandbox、write scope、artifact clipping、trace/report metadata。**危险命令黑名单**在 `run_shell` 执行前自动拦截。
- Session event bus 记录 runtime mode、tool decisions、context usage、worker notifications、skill activity、compaction 和 evidence 相关事件。
- Token 估算使用 CJK-aware 算法（中文字符 ~1.5 token/字，ASCII ~0.25 token/字符），通过 `context_usage.estimate_tokens()` 统一计算。
- `SessionStore` 已提取为独立模块 `repo_harness/session_store.py`，**原子写入**（tempfile + os.replace），持久化前自动 **secret 脱敏**。
- **可观测性**：`/metrics` 命令展示工具调用统计、循环检测、热路径、失败率告警、token 消耗；快照自动保存到 `.repo-harness/metrics/`。

## 运行时隐式行为

以下行为在代码中实现但用户可能不会主动感知，维护者需要了解。

### 自动触发的行为

- **自动历史压缩**：当 prompt token 超过模型 context window 时，`Engine.run_turn()` 在调用模型前自动触发 `compact_history(trigger="context_overflow")`，压缩旧 history 并重建 prompt。用户不会看到明确提示，仅在 event stream 中有 `history_auto_compacted` 事件，`/metrics` 命令会显示最近一次压缩事件。
- **记忆自迭代**：每次 agent 完成一轮后，`run_memory_self_iteration()` 自动扫描 episodic notes，将符合 durable pattern 的笔记推入 Review Queue。用户需主动运行 `/memory review` 才能看到候选项。这不会直接写入 durable topics。
- **Durable memory 自动提取**：turn 结束时 `promote_durable_memory()` 检查用户消息是否包含"记住/保存/记录"等意图词，从 final answer 中提取结构化记忆候选。
- **Prefix 自动刷新**：每次 `_build_prompt_and_metadata()` 都会调用 `refresh_prefix()`，如果工作区 fingerprint 变化则重建 prefix。
- **Worker 通知自动排空**：Engine 主循环每轮开始和结束时都调用 `_drain_worker_notification_events()`，将完成的 worker 结果注入 session history。
- **Step limit 自动请求模型总结**：达到 `max_steps` 后不是直接停止，而是请求模型生成总结性 final answer。
- **Checkpoint 自动创建**：在以下时机自动创建 checkpoint：tool 执行后、freshness_mismatch、workspace_mismatch、context_reduction、run_finished、abort。

### 工具系统隐式行为

- **Tool Policy 隐式拒绝**：`ToolPolicy` 在以下情况静默拒绝工具调用：① `patch_file`/`write_file` 覆盖已有文件前未先 `read_file`（`prior_read_required`）；② `run_shell` 被检测为普通搜索/读取操作（应使用 `search`/`read_file`）；③ 最近 5 次中 3 次相同工具+参数调用（滑动窗口重复检测）。
- **delegate 子 agent 强制只读**：delegate 工具创建的子 agent 强制以 `read_only=True`、`approval_policy="never"` 运行，且深度限制为 1（`max_depth=1`，子 agent 不能再 delegate）。
- **Worker 类型限制**：Plan mode 下只允许 `Explore` 类型的 worker，不允许 `worker`（写入型）。
- **run_shell bash 优先**：在 Windows 上也会尝试使用 Git Bash（`C:\Program Files\Git\bin\bash.exe`）而非 cmd.exe，bash 不可用时 fallback 到 `shell=True`。
- **search rg fallback**：`search` 工具优先使用 `rg`（ripgrep），如果系统未安装 `rg`，自动 fallback 到 Python 遍历文件搜索。
- **ask_user callback fallback**：如果 `ask_user_callback` 未设置且有 `choices`，默认选第一个 choice；如果没有 choices，尝试 `input()`。
- **_ExplicitStoreAction**：CLI 参数使用自定义 Action，可以区分"用户显式传入"和"默认值"，影响配置优先级链。

### 安全相关隐式行为

- **PATH 消毒**：`shell_env()` 方法在构建子进程环境变量时，通过 `_sanitize_path()` 过滤 PATH 中的临时目录（`/tmp`、`AppData\Local\Temp` 等），防止 PATH 注入攻击。
- **项目级配置安全警告**：如果项目级 `.repo-harness.toml` 覆盖了 `base_url` 或 `provider`，`resolve_runtime_config()` 会在 stderr 输出警告，提醒用户确认是否可信。
- **Sandbox excluded_commands shell 元字符保护**：如果命令包含 `$(`、`` ` ``、`\` 等 shell 元字符，即使匹配 excluded_commands 模式也不会被排除（防止绕过沙箱）。
- **read_only agent 路径逃逸仍会 raise**：`agent.path()` 在 read_only 模式下仍会检查 `is_relative_to(self.root)`，只是 run_tool 层面在权限检查阶段拦截。
- **Auto Issue Fix prompt injection 防护**：issue body 中的 `<tool>`、`<final>`、`<plan>` 标签会被转义为全角字符，防止 prompt injection。

### 容错和降级

- **Session 文件损坏静默降级**：`SessionStore.load()` 在 JSON 解析失败时返回空 session（带 `_load_error` 字段），不会崩溃。下次保存时覆盖损坏文件。
- **Memory 文件损坏静默跳过**：`load_index()` / `load_topic_notes()` 在文件损坏时静默跳过，记录到 `_corruption_warnings` 列表。
- **Windows 文件替换重试**：`RunStore._replace_with_windows_retry()` 对 Windows 的 `PermissionError`（winerror 5/32）做短重试，最多等约 385ms。
- **`max_tokens` 别名**：配置文件中的 `max_tokens` 会被当作 `max_new_tokens` 的别名处理。
- **`REPO_HARNESS_HOME`**：可通过环境变量覆盖 home 目录来改变全局配置路径。
- **`.env` 支持 `export` 前缀**：`.env` 文件中 `export KEY=VALUE` 格式被静默支持。
- **Claude Code skills 兼容**：从 `~/.claude/skills/` 发现技能，`ImportError` 时静默跳过。
- **Auto Issue Fix facade 代理模式**：`guided_repl.py` 通过 `sys.modules.get("repo_harness.auto_issue_fix")` 查找 facade 模块的 `run_auto_issue_fix`，如果 facade 被 monkey-patch 则使用替换实现。

### 被吞掉的异常（维护者需知）

以下异常被捕获后不会传播到用户，维护者调试时需要注意：

| 位置 | 异常类型 | 处理方式 |
| --- | --- | --- |
| `cli.py` prompt_toolkit 初始化 | `Exception` | fallback 到 `input()`，写 debug 日志 |
| `tool_policy.py` `_has_fresh_read()` | `Exception` | 返回 False（拒绝操作），写 debug 日志 |
| `engine_helpers.py` `maintain_memory_safely()` | `Exception` | 记录到 `last_memory_maintenance` 和 trace |
| `engine_helpers.py` `step_limit_summary` | `Exception` | 返回 None，使用默认停止消息 |
| `cli.py` `_memory_explain_text()` | `Exception` | 返回提示文本 |
| `runtime.py` workspace snapshot 单文件 | `Exception` | `continue` 跳过该文件 |

## Provider 和配置

支持 provider：

- `openai`
- `chat-completions`
- `anthropic`
- `deepseek`
- `ollama`

配置优先级：

```text
CLI 显式参数 > process env / 项目 .env > 项目 .repo-harness.toml > 全局 config > 默认值
```

`openai` 代表 Responses API；`chat-completions` 代表 `/chat/completions` 兼容后端，MiMo 等服务应走这一独立 provider。DeepSeek 是一等 provider，底层走 Anthropic-compatible client。默认 `max_steps=50`，`max_new_tokens` 按 provider 推断。

## Tool / Permission / Sandbox

工具执行统一进入 core executor：

- `approval_policy="ask"` 对同一 risky tool 只触发一次审批。
- shell read/search 被 policy 拦截，鼓励结构化 `read_file` / `search`。
- **危险命令黑名单**：`run_shell` 执行前检查 20+ 危险模式（`rm -rf /`、`curl | sh`、`shutdown` 等），链式命令拆分后逐条检查。
- **ReDoS 防护**：`search` 默认使用 `--fixed-strings` 字面匹配，pattern 长度限制 200 字符。
- 既有文件写入要求 fresh read；**TOCTOU 修复**：`patch_file` 执行时重新 `resolve()` 路径。
- 重复工具调用改为**滑动窗口**检测（最近 5 条中出现 3 次相同调用）。
- 多 tool-call 按顺序执行，partial failure 写入 trace。
- 长 shell 输出会裁剪展示，并把完整输出写入 run artifact。
- 所有工具错误信息包含实际路径；捕获 `OSError` / `TimeoutExpired` 返回结构化错误。
- **PATH 清理**：子进程环境过滤临时目录。

Sandbox 默认为 `best_effort`。支持 `off`、`best_effort`、`read_only`、`required`。`required` 在后端不可用时 fail closed；Windows fallback 写入明确 metadata 并输出 stderr 警告。bubblewrap 沙箱默认启用 `--unshare-net` 网络隔离。v4 修复了 `excluded_commands` 可通过 shell 元字符（`$(`、`` ` ``、`\`、`${`）绕过的安全漏洞。

## Skills、Workers 和 REPL

Skills 从 `skills/<name>/SKILL.md` 与 `.repo-harness/skills/<name>/SKILL.md` 发现。v4 新增 Claude Code Skill 兼容层（`features/claude_code_skills.py`），同时从 `~/.claude/skills/` 发现 SKILL.md 文件。Claude Code 工具名称自动映射到 RepoHarness 等价物（`Read` → `read_file`，`Bash` → `run_shell` 等）。frontmatter 支持常见 YAML list；`allowed_tools` 会同步刷新 prompt 工具列表和实际 permission gate。

Workers 是 session-scoped 子任务。Explore worker 只读；write worker 必须声明 `write_scope`。Worker 支持后台生命周期、continue、stop、shutdown、running send guard、notifications、artifacts 和 parent report 汇总。Worker 默认最大 30 步，防止僵尸线程。

**编排原语**（v6 新增）：

- `parallel(tasks)`：并行执行多个 worker，等待全部完成，返回结构化结果。
- `pipeline(stages)`：串行执行，前一个输出通过 `{input}` 传给下一个；stage 失败时后续标记为 skipped。
- `dag(tasks)`：支持依赖关系的并行执行（拓扑排序 + 批次并行 + 失败阻断下游）。
- `post_message(channel, msg)` / `read_messages(channel)`：worker 间消息队列。

v4 移除了 Textual TUI 框架，改为基于 `rich` 的增强 REPL。REPL 现在直接消费 `engine.run_turn()` 事件流，实时显示工具调用和结果。`ReplFacade`（`repl_facade.py`）提供 snapshot、suggest_commands、ask_user、run_turn 等核心抽象。Slash completion、normal turn、ask_user prompt 和 worker notification 不走独立行为路径。v6 新增 `/metrics` 命令展示工具调用统计和 session token 消耗。

## Auto Issue Fix 编排层

Auto Issue Fix 是当前版本和 v3 能力完善同等级的重要更新。`repo-harness auto-issue-fix` 和 REPL `/auto-issue-fix` 复用现有 CLI 分发、provider 配置、RepoHarness runtime、证据目录和脱敏策略，不绕过 permission gate、tool policy、sandbox 或 RunStore。普通 REPL 中不带参数的 `/auto-issue-fix` 会进入引导式流程；非交互环境仍要求显式传入 `--repo` / `--issue` 或 discovery 参数。

v6 重构为 5 stage 流水线：`_stage_analyze`（issue 发现）→ `_stage_clone_and_baseline`（克隆 + 基线测试）→ `_stage_fix`（agent 修复，可重试）→ `_stage_review`（测试 + diff + 审查门）→ `_stage_commit_push_pr`（commit + push + PR）。review gate 阻塞时不重试，仅测试失败时自动重试（默认最多 2 次）。issue body 通过 `_sanitize_for_prompt()` 转义 `<tool>`/`<final>`/`<plan>` 标签防止 prompt injection。测试执行通过 `check_dangerous_command()` 检查危险命令。

当前已实现的是真实执行 + dry-run 预演：`AutoIssueFixConfig` 归一化用户意图，`GhCliBackend` 负责 GitHub CLI 接入，`AutoIssueFixReviewGate` 记录自动审查门，`AutoIssueFixRunRecord` 记录可移植状态，模板渲染生成 `run-record.md`、`pr-body.md`、`formal-report-summary.md`、`run-record.json` 和失败时的 `pr-ready-fallback.md`。默认报告使用 `<workspace>`、`<repo>`、`<evidence_dir>` 等占位符，并对 token、cookie、API key 和 secret-shaped 内容做 `<redacted>` 脱敏。

Auto Issue Fix 代码按职责拆成 `config`、`github_backend`、`security`、`workspace`、`reviewer`、`evidence`、`runner` 和 `guided_repl`，包入口只保留 public facade 和兼容导出。这样后续替换 GitHub backend、增强 runner 或改进 REPL 引导时，不需要重新耦合证据模板和配置模型。

自动审查门是两种模式共享的治理层。`review-gated` 是自动审查通过后继续等待人确认；`draft-auto` 是自动审查通过后减少人工暂停。任一阶段出现 `block` verdict 都必须停止运行并生成 fallback 证据。

`review-gated` 是推荐的默认使用方式；`draft-auto` 仍只创建 draft PR，不能绕过自动审查或人的最终 review。Auto Issue Fix 输出的是候选修复和证据包，patch、测试日志和 PR 描述都需要人工严格验证后再提交给上游维护者。

每次运行会生成 `reviews/review-<stage>.json`、`reviews/review-<stage>.md`、`decision-log.jsonl` 和 `checkpoint.json`。真实执行还会生成 `issue.json`、`baseline-repro.log`、`fix-run.log`、`test-after-fix.log`、`git-diff.patch` 和成功时的 `pr-url.txt`。

公开 `pr-body.md` 与本地证据分离：PR 描述只保留维护者需要看到的 summary、issue、changed files、validation、scope/risk 和 maintainer notes；工具链、模型、实验记录、trace 和 evidence 细节留在本地 run record / formal report。`maintainer-trust` 审查门负责阻断不适合公开提交的 PR title、body、commit message 或 branch。

## Evidence 和 Release Gate

`RunEvidence` 提供结构化结果对象和 public CLI/scripted provider 验收。public CLI scripted task 会验证：

- changed file
- runtime report
- trace
- session events
- state dir

Business dogfood 默认 fake/scripted provider，场景合同为：

- `order_pricing_bugfix`
- `release_readiness_review`
- `incident_resume_fix`

Live provider 必须显式 opt-in。

## 记忆治理边界

RepoHarness 的 durable memory 必须经人工审核：

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

`/remember`、`/memory organize`、skills、workers、evidence 和 memory self-iteration 只能写 Review Queue candidates，不能直接写 `.repo-harness/memory/topics/*.md`。

Memory Pack、Explainable Retrieval、Fuzzy Lexical Retrieval 是 RepoHarness 的保留优势。

## Provider onboarding

`repo-harness provider probe`、`repo-harness provider setup` 和 `repo-harness provider doctor` 属于 CLI/config/provider 装配层，不进入 runtime tool loop。probe 默认根据 endpoint 或已知厂商根路径推断 provider，不发送模型请求；只有显式 `--smoke` / `--allow-live-probe` 才执行最小 live request。setup 只写入 provider、model、base URL 和 API key 环境变量名；doctor 读取同一套 config 解析链路，验证 key 是否存在，并可选执行最小 smoke request。Provider Registry 是这些入口的单一事实源，用于降低模型接入摩擦，但不改变 OpenAI Responses、Chat Completions、Anthropic、DeepSeek 和 Ollama 的 provider 边界。
