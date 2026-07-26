# RepoHarness 架构概览

## 文档目的

本文记录 RepoHarness 当前架构边界、运行工件和维护规则。历史记录只保留必要事实；当前实现以 `repo-harness`、`repo_harness` 和 `.repo-harness/` 为准。

Agent Harness v1 的核心概念仍然保留：一次任务会生成 task state、trace 和 report，以便复现和审计。

## 当前架构记录：2026-05-29 v4 代码清理、安全加固与 Claude Code Skill 兼容

RepoHarness 的公共 API 仍然是 `RepoHarness.ask()`、`repo-harness` CLI 和 `python -m repo_harness`。REPL、public CLI scripted evidence、workers 和 release evidence 共用同一套 runtime、permission、tool policy、session events、trace/report 工件。

核心链路：

- CLI 读取显式参数、环境变量、项目 `.env`、项目 `.repo-harness.toml`、全局 `%USERPROFILE%\.repo-harness\config.toml`，并按固定优先级合并。
- Runtime 构建 prompt prefix、workspace context、memory context、skills section、tool list 和 active tool profile。
- Model 输出解析为 final answer、tool calls、ask_user 或 control flow。
- Core tool executor 统一执行 permission gate、tool policy、sandbox、write scope、artifact clipping、trace/report metadata。
- Session event bus 记录 runtime mode、tool decisions、context usage、worker notifications、skill activity、compaction 和 evidence 相关事件。
- Token 估算使用 CJK-aware 算法（中文字符 ~1.5 token/字，ASCII ~0.25 token/字符），通过 `context_usage.estimate_tokens()` 统一计算。
- `SessionStore` 已提取为独立模块 `repo_harness/session_store.py`，便于独立测试和复用。

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
- 既有文件写入要求 fresh read。
- 重复工具调用有 guard。
- 多 tool-call 按顺序执行，partial failure 写入 trace。
- 长 shell 输出会裁剪展示，并把完整输出写入 run artifact。

Sandbox 支持 `off`、`best_effort`、`read_only`、`required`。`required` 在后端不可用时 fail closed；Windows fallback 写入明确 metadata。`read_only` 下不执行任何 shell 命令，`excluded_commands` 在该模式下不提供豁免——过滤命令字符串无法保证「只做一件事」，见 ADR-007。

## Skills、Workers 和 REPL

Skills 从 `skills/<name>/SKILL.md` 与 `.repo-harness/skills/<name>/SKILL.md` 发现。v4 新增 Claude Code Skill 兼容层（`features/claude_code_skills.py`），同时从 `~/.claude/skills/` 发现 SKILL.md 文件。Claude Code 工具名称自动映射到 RepoHarness 等价物（`Read` → `read_file`，`Bash` → `run_shell` 等）。frontmatter 支持常见 YAML list；`allowed_tools` 会同步刷新 prompt 工具列表和实际 permission gate。

Workers 是 session-scoped 子任务。Explore worker 只读；write worker 必须声明 `write_scope`。Worker 支持后台生命周期、continue、stop、shutdown、running send guard、notifications、artifacts 和 parent report 汇总。

v4 移除了 Textual TUI 框架，改为基于 `rich` 的增强 REPL。REPL 现在直接消费 `engine.run_turn()` 事件流，实时显示工具调用和结果。`ReplFacade`（`repl_facade.py`）提供 snapshot、suggest_commands、ask_user、run_turn 等核心抽象。Slash completion、normal turn、ask_user prompt 和 worker notification 不走独立行为路径。

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

`/remember`、`/memory organize`、skills、workers、evidence 和 memory self-iteration 只能写 Review Queue candidates，不能直接写 `.repo-harness/memory/topics/*.md`。

Memory Pack、Explainable Retrieval、Fuzzy Lexical Retrieval 是 RepoHarness 的保留优势。


## Provider onboarding

`repo-harness provider probe`、`repo-harness provider setup` 和 `repo-harness provider doctor` 属于 CLI/config/provider 装配层，不进入 runtime tool loop。probe 默认根据 endpoint 或已知厂商根路径推断 provider，不发送模型请求；只有显式 `--smoke` / `--allow-live-probe` 才执行最小 live request。setup 只写入 provider、model、base URL 和 API key 环境变量名；doctor 读取同一套 config 解析链路，验证 key 是否存在，并可选执行最小 smoke request。Provider Registry 是这些入口的单一事实源，用于降低模型接入摩擦，但不改变 OpenAI Responses、Chat Completions、Anthropic、DeepSeek 和 Ollama 的 provider 边界。
