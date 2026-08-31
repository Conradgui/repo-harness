# RepoHarness 架构概览

## 文档目的

本文记录 RepoHarness 当前架构边界、运行工件和维护规则。历史记录只保留必要事实；当前实现以 `repo-harness`、`repo_harness` 和 `.repo-harness/` 为准。

Agent Harness v1 的核心概念仍然保留：一次任务会生成 task state、trace 和 report，以便复现和审计。

## 当前架构记录：2026-05-29 v4 代码清理、安全加固与 Claude Code Skill 兼容

> **v6 更新**：prompt 纯计算提取到 `core/prompt_builder.py`，checkpoint 纯计算提取到 `core/checkpoint_builder.py`，context window 支持环境变量扩展。详见 changelog-draft.md。
>
> **v7 更新**：secret 环境变量脱敏逻辑提取到 `core/secret_sanitizer.py`；sandbox hardening 跨 `auto_issue_fix` / `cli` / `tool_policy` / `workspace` / `context_manager` 落实（read_only 直接阻止 run_shell、关闭 .env 覆盖与 fail-open 回退，见 ADR-007）；`RepoHarness` 保留上述 builder 的瘦转发器。详见 changelog-draft.md。
>
> **v8 更新**：Harness Engineering 修复轮（审计 8 findings 全关闭）落地——act 完成验证门（ADR-008）、自主场景外部 clone 默认受限沙箱（ADR-009）、审批路径绑定信任、ProviderError 双层重试、session 原子写与收尾链异常保护、abort 协议接线、auto-compact 接线；真实 CLI 用户旅程 e2e（本地 mock provider 驱动子进程）补充验证并修复三处旅程断点：/help 渲染与命令表双源漂移、/memory review 空输入死循环、REPL 输入流被 prompt_toolkit 与裸 input() 撕开。

RepoHarness 的公共 API 仍然是 `RepoHarness.ask()`、`repo-harness` CLI 和 `python -m repo_harness`。REPL、public CLI scripted evidence、workers 和 release evidence 共用同一套 runtime、permission、tool policy、session events、trace/report 工件。

核心链路：

- CLI 读取显式参数、环境变量、项目 `.env`、项目 `.repo-harness.toml`、全局 `%USERPROFILE%\.repo-harness\config.toml`，并按固定优先级合并。
- Runtime 构建 prompt prefix、workspace context、memory context、skills section、tool list 和 active tool profile。Prompt 纯计算（文本构建、工具签名、工具过滤）提取到 `core/prompt_builder.py`，checkpoint 纯计算提取到 `core/checkpoint_builder.py`。
- Model 输出解析为 final answer、tool calls、ask_user 或 control flow。
- Core tool executor 统一执行 permission gate、tool policy、sandbox、write scope、artifact clipping、trace/report metadata。
- Session event bus 记录 runtime mode、tool decisions、context usage、worker notifications、skill activity、compaction 和 evidence 相关事件。
- Engine 的中止协议闭环：`runtime.abort_current_turn()` 置位 abort 标志后，REPL `/stop`、worker stop 与 Ctrl-C（CLI 转受控中止：生成器存活时 drain 到终态，已死时退回中断持久化兜底）都汇入同一机制——正在排队的工具调用被 run_tool 前置检查安全跳过，engine 走 `finish_stopped_run("aborted")` 受控收尾，turn 开始时清除残留标志。
- Token 估算使用 CJK-aware 算法（中文字符 ~1.5 token/字，ASCII ~0.25 token/字符），通过 `context_usage.estimate_tokens()` 统一计算。
- `SessionStore` 已提取为独立模块 `repo_harness/session_store.py`，便于独立测试和复用。session 写入采用 tempfile + `os.replace` 原子替换（与 run_store 同一标准）并通过 store 级锁串行化 worker 线程与主线程的并发保存；损坏文件在 `load()` 抛出受控的 `SessionLoadError`。engine 的 final 收尾链有异常保护：持久化环节失败时 run 降级为 `failed`/`persistence_error` 终态并落盘 task_state 与最小 report；CLI 捕获 Ctrl-C 后保底保存 session 并把悬在 `running` 的 run 标记为 `interrupted`。
- Context window 支持通过 `REPO_HARNESS_EXTRA_CONTEXT_WINDOWS` 环境变量扩展，用户可注册新模型无需改代码。
- auto-compact 有三个触发信号：history 的 raw 需求超过其 section 预算（真实运行的主要信号）、本轮 prompt 触发预算削减、输入 token 占用越过 `AUTO_COMPACT_THRESHOLD`。任一命中时 engine 先执行 `compact_history(trigger="auto")` 再重建 prompt（`auto_compaction` 事件 + trace），而不是任由预算静默裁掉历史。注意 token 占用比例按 rendered 文本估算，而 section 预算先于估算裁剪了 history——单看该比例在真实预算计算下恒低于阈值（e2e 曾复现：注入 usage 的单测绿、真实 CLI 永不触发），所以 raw 需求超预算才是可信的压力信号。预算削减确实发生时，prompt 在当前请求前注入模型可见的 `[context notice]` 声明。
- Model client 类（OpenAI/Chat Completions/Anthropic）的 `__repr__` 对 api_key 脱敏，防止通过 repr 泄露。

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

模型后端的失败统一抛 `ProviderError`（`providers/errors.py`）：网络类失败 `code="network_error"`、HTTP 类 `code="http_<status>"`（status 在 `RETRYABLE_HTTP_CODES` 内视为 retryable）、空响应 `code="empty_response"`，均携带 provider/model/base_url/attempts/retry_count 元数据。重试分两层：provider 适配层对网络与 retryable HTTP 做 3 次快速退避；engine 对 `retryable=True` 的错误每个 code 再给一次 turn 级重试（`model_retry_scheduled` 事件），重试后仍失败则走受控 `model_error` 失败收尾，错误元数据进入 report 与 trace。

## Tool / Permission / Sandbox

工具执行统一进入 core executor：

- `approval_policy="ask"` 的 a(llow) 升级按 (tool, path) 绑定：同一写入路径免重复提示，换路径或换工具重新审批；`run_shell` 无会话级信任，每条命令单独审批。
- 审批提示展示完整工具参数（不截断）；升级发出 `approval_escalated` 审计事件，`/untrust` 可撤销会话内全部升级。
- shell read/search 被 policy 拦截，鼓励结构化 `read_file` / `search`。
- 既有文件写入要求 fresh read。
- 重复工具调用有 guard。
- 多 tool-call 按顺序执行，partial failure 写入 trace。
- act 模式 final 过完成验证门：本 turn 有改动且改动后无验证命令时，final 被拦截并降级为 runtime_notice（证据必须覆盖最后一次改动；worker 与 AIF 的汇报层豁免），见 [ADR-008](../decisions/008-act-完成宣告需要验证证据.md)。
- 长 shell 输出会裁剪展示，并把完整输出写入 run artifact。

Sandbox 支持 `off`、`best_effort`、`read_only`、`required`。`required` 在后端不可用时 fail closed（`sandbox_unavailable` 事件 + 拒绝执行）；Windows fallback 写入明确 metadata。`read_only` 下不执行任何 shell 命令，`excluded_commands` 在该模式下不提供豁免——过滤命令字符串无法保证「只做一件事」，见 ADR-007。bubblewrap 后端默认断网（argv 带 `--unshare-net`），`allow_network` 是唯一的显式出网开关；Auto Issue Fix 对未显式声明 `mode` 的外部 clone 默认使用受限沙箱（required + bubblewrap），显式 `mode = "off"` 依旧被尊重，见 [ADR-009](../decisions/009-自主场景的外部clone默认受限沙箱.md)。

## Skills、Workers 和 REPL

Skills 从 `skills/<name>/SKILL.md` 与 `.repo-harness/skills/<name>/SKILL.md` 发现。v4 新增 Claude Code Skill 兼容层（`features/claude_code_skills.py`），同时从 `~/.claude/skills/` 发现 SKILL.md 文件。Claude Code 工具名称自动映射到 RepoHarness 等价物（`Read` → `read_file`，`Bash` → `run_shell` 等）。frontmatter 支持常见 YAML list；`allowed_tools` 会同步刷新 prompt 工具列表和实际 permission gate。

Workers 是 session-scoped 子任务。Explore worker 只读；write worker 必须声明 `write_scope`。Worker 支持后台生命周期、continue、stop、shutdown、running send guard、notifications、artifacts 和 parent report 汇总。

v4 移除了 Textual TUI 框架，改为基于 `rich` 的增强 REPL。REPL 现在直接消费 `engine.run_turn()` 事件流，实时显示工具调用和结果。`ReplFacade`（`repl_facade.py`）提供 snapshot、suggest_commands、ask_user、run_turn 等核心抽象。Slash completion、normal turn、ask_user prompt 和 worker notification 不走独立行为路径。

REPL 的输入读取器保持唯一：prompt_toolkit（行编辑/补全/历史）只在 stdin 是 tty 时启用，管道/CI 等非交互环境一律退回 `input()`——pt 在管道上会预读缓冲，与 `/memory review`、审批提示等交互路径的 `input()` 撕开同一个输入流（e2e 曾复现：输入行被 pt 吞掉再当作 REPL 消息吐出）。`/memory review` 对空输入（EOF 或 Ctrl-C 被吞）的语义是离开 review 并保留候选队列，而不是循环追问——交互循环对不可用的输入流必须有终止路径。

## Auto Issue Fix 编排层

Auto Issue Fix 是当前版本和 v3 能力完善同等级的重要更新。`repo-harness auto-issue-fix` 和 REPL `/auto-issue-fix` 复用现有 CLI 分发、provider 配置、RepoHarness runtime、证据目录和脱敏策略，不绕过 permission gate、tool policy、sandbox 或 RunStore。普通 REPL 中不带参数的 `/auto-issue-fix` 会进入引导式流程；非交互环境仍要求显式传入 `--repo` / `--issue` 或 discovery 参数。

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

`/remember`、`/memory organize`、skills、workers、evidence 和 memory self-iteration 只能写 Review Queue candidates，不能直接写 `.repo-harness/memory/topics/*.md`。该边界由 `PermissionChecker` 的运行时状态目录禁写（`state_dir_write_guard`，先于 `write_scope` 求值）强制执行：`write_file`/`patch_file` 对 `.repo-harness/` 下任何路径一律拒绝，`write_scope` 显式授权也无法绕过；唯一例外是 plan 模式写 active plan 文件。

Memory Pack、Explainable Retrieval、Fuzzy Lexical Retrieval 是 RepoHarness 的保留优势。


## Provider onboarding

`repo-harness provider probe`、`repo-harness provider setup` 和 `repo-harness provider doctor` 属于 CLI/config/provider 装配层，不进入 runtime tool loop。probe 默认根据 endpoint 或已知厂商根路径推断 provider，不发送模型请求；只有显式 `--smoke` / `--allow-live-probe` 才执行最小 live request。setup 只写入 provider、model、base URL 和 API key 环境变量名；doctor 读取同一套 config 解析链路，验证 key 是否存在，并可选执行最小 smoke request。Provider Registry 是这些入口的单一事实源，用于降低模型接入摩擦，但不改变 OpenAI Responses、Chat Completions、Anthropic、DeepSeek 和 Ollama 的 provider 边界。
