# RepoHarness

> Python 3.10+ | MIT License | ruff 0 error · 测试全绿

一个运行在本地仓库里的 coding agent runtime。它通过受约束的工具读文件、改文件、跑命令，把会话、运行工件、记忆和审计信息留在 `.repo-harness/` 下。

**它解决的不是"让模型写代码"，而是"让 agent 安全地改动一个真实仓库"之间那层工程。** 控制循环本身只有 448 行；其余的代码量花在模型不会替你处理的事情上——输出格式纠错、上下文超限时的自动压缩、工具输出截断、重复调用检测、路径越界收敛、以及模型自己填的参数带来的注入面。

```bash
uv sync
uv run repo-harness --repl
```

新手完整流程见 [新手指南](docs/getting-started.md)，设计取舍与实现见 [整体方案](docs/spec/整体方案.md)。

## 三个设计取舍

**权限决策收敛到单点。** 所有工具调用经 `PermissionChecker.check()` 求值，工具实现里不自行判断能不能做。代价是这个函数会长；收益是想知道"什么情况下 agent 能写文件"，读一个函数就够。这个取舍被一次真实事故验证过——曾有人在函数第一行加了无条件 `deny`，让下方的细粒度校验变成永不可达的死代码，**因为决策集中，这个矛盾一眼可见**。

**拒绝回传模型，而不是抛异常。** 权限拒绝把错误码作为下一轮输入交还模型，模型据此换方法。用户看到的是 agent 调整策略，不是崩溃。一个动不动就终止的权限系统，用户的第一反应是全放开。

**为复盘而设计，不为复现。** agent 行为非确定性，要求可复现是与模型本质对抗。每次运行产出独立的 `task_state.json` / `trace.jsonl` / `report.json`——能复盘才是可达成的目标。

## 从用户卡点倒推的交互设计

provider 配置是新手最高频的卡点，而且失败信号有误导性：HTTP 404 看起来像服务不可用，实际往往是把只支持 `/chat/completions` 的模型配成了 Responses provider。用户会去查网络、查域名，问题却在配置里。

所以不做"配置向导"，而是拆成三个命令，各自回答一个用户能自己判断的问题：

| 命令 | 用户此刻的困惑 |
|---|---|
| `provider probe` | 不知道该选哪个 —— 从 endpoint 路径反推 |
| `provider setup` | 知道选什么但不确定怎么写 —— 只存环境变量名，不存 key |
| `provider doctor` | 配好了但跑不通 —— 告诉你 401/404 各意味着什么 |

`probe` 默认不发真实请求，避免用户在探测阶段产生计费。

## 版本迭代

v4 / v5 的详细变更见 [changelog-draft.md](docs/maintainer-prep/changelog-draft.md)。v6 完成了 God Object 解体推进、深度审计与安全加固（builder 提取、context window 扩展、异常收窄）；v7 收尾了 builder 提取、Sandbox 加固与测试质量门禁（脱敏逻辑提取为 `core/secret_sanitizer.py`、跨模块收敛命令执行边界、收紧 5 处弱断言并新增中断恢复 / 模型错误可见性场景测试，509 passed / 1 skipped、ruff 0 error）。本轮重建的完整记录见 [交付文档](docs/delivery/README.md)。

## 产品边界

- CLI 入口是 `repo-harness`，模块入口是 `python -m repo_harness`，Python 包名是 `repo_harness`。
- 本地状态目录只使用 `.repo-harness/`。
- 长期记忆必须经过 Review Queue；`/remember`、`/memory organize`、skills、workers、evidence 和自动整理都不能直接写 durable topics。
- Memory Pack、Explainable Retrieval、Fuzzy Lexical Retrieval 和 Review Queue 是 RepoHarness 的核心优势，不因外部兼容诉求而降级。
- Auto Issue Fix v2 提供真实执行模式和 dry-run 预演：CLI/REPL 入口、issue 获取、隔离 clone、RepoHarness 修复、测试、自动审查门、draft PR、脱敏和路径普适化已落地。

## 能力概览

| 能力 | 面向的问题 | RepoHarness 的处理方式 |
| --- | --- | --- |
| 本地受控 agent runtime | Agent 需要读写仓库和运行命令，但不能失控执行。 | 统一经过 tool executor、permission gate、tool policy 和 sandbox。 |
| Provider 配置闭环 | 不同模型厂商 endpoint、协议和 key 管理容易混乱。 | 提供 provider setup / probe / doctor，并只保存环境变量名，不写入 secret。 |
| Memory governance | 长期记忆如果自动写入，会污染后续推理。 | 所有 durable memory 必须先进入 Review Queue，再由人 accept/edit。 |
| Explainable retrieval | 记忆命中如果不可解释，很难审计。 | 保留 score breakdown 和 selected explanations，支持 `/memory_explain`。 |
| Auto Issue Fix | AI 修 issue 需要真实执行能力，也需要证据和门禁。 | 支持 dry-run、review-gated、draft-auto、自动审查门、fallback evidence 和 draft PR。 |
| Claude Code Skill 兼容 | 不同 agent 平台的 skill 生态割裂。 | 自动从 `~/.claude/skills/` 发现 SKILL.md，工具名称自动映射。 |
| Release evidence | 关键路径需要可复现验证。 | 通过 scripted provider、dogfood、focused tests 和 release evidence 验证关键路径。 |

长期记忆治理路径固定为：

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

完整新手流程见 [docs/getting-started.md](docs/getting-started.md)。

## 安装

需要 Python 3.10+。推荐使用 `uv`：

```bash
uv sync
uv run python -m repo_harness --help
```

也可以安装为可编辑包：

```bash
pip install -e .
repo-harness --help
```

## 快速启动

在当前仓库里进入交互模式：

```bash
uv run repo-harness
```

指定工作区：

```bash
uv run repo-harness --cwd /path/to/repo
```

执行一次性任务：

```bash
uv run repo-harness "inspect the failing tests and propose a fix"
```

Windows PowerShell 示例：

```powershell
uv run repo-harness --cwd C:\path\to\repo
uv run repo-harness "summarize this repository"
```

## Provider 配置

如果你手上已经有一个模型 API key，先看厂商文档里的 endpoint，再选择 provider。配置文件里的 `base_url` 只填到厂商给出的版本根路径，例如 `https://example.com/v1`；RepoHarness 会按 provider 自动追加 `/responses`、`/chat/completions` 或对应路径。`provider setup` / `provider probe` 命令可以接收完整 endpoint 路径，并在写入配置时自动剥离成版本根路径。

RepoHarness 支持五类 provider：

- `openai`：OpenAI-compatible Responses API；厂商文档路径是 `/v1/responses` 时使用。
- `chat-completions`：Chat Completions-compatible API；厂商文档路径是 `/v1/chat/completions` 时使用，很多国产模型属于这一类。
- `anthropic`：Anthropic-compatible Messages API；厂商文档路径是 Anthropic `/messages` 时使用。
- `deepseek`：DeepSeek 一等 provider，默认走 Anthropic-compatible client。
- `ollama`：本地 Ollama。

推荐的配置步骤：

1. 把 API key 放进环境变量，例如 `MY_MODEL_API_KEY`。
2. 如果不确定 provider，先运行 `repo-harness provider probe` 根据 endpoint 或已知厂商根路径推断 provider。
3. 运行 `repo-harness provider setup`，或用 `provider probe --write` 生成 `.repo-harness.toml`。
4. 运行 `repo-harness provider doctor` 检查配置；需要真实 smoke request 时加 `--smoke`。
5. 启动 `uv run repo-harness --repl`。

```bash
repo-harness provider probe --base-url https://<vendor-host>/v1 --model <model> --api-key-env MY_MODEL_API_KEY
repo-harness provider probe --base-url https://<vendor-host>/v1 --model <model> --api-key-env MY_MODEL_API_KEY --write
repo-harness provider probe --base-url https://<vendor-host>/v1 --model <model> --api-key-env MY_MODEL_API_KEY --smoke
repo-harness provider setup --base-url https://<vendor-host>/v1/chat/completions --model <model> --api-key-env MY_MODEL_API_KEY
repo-harness provider doctor
repo-harness provider doctor --smoke
```

`provider probe` 默认不发送模型请求，只根据 endpoint 后缀或已知厂商根路径推断 provider；只有加 `--smoke` 或 `--allow-live-probe` 才会发送一次真实最小模型请求，可能产生计费、日志或 rate limit。默认不写文件，只有加 `--write` 才更新配置。`provider setup` 只写入环境变量名，不会把 API key 值写进配置文件；如果 `.repo-harness.toml` 已存在，它会更新 provider 配置并保留 `max_steps`、`[sandbox]` 和其他 provider section。`provider doctor` 只报告 key 是否存在，不打印 secret。

如果只给一个未知厂商的版本根路径，例如 `https://models.example.com/v1`，RepoHarness 无法可靠判断协议；这时请传 `--provider`，或把厂商文档里的完整 endpoint 路径交给 `provider setup` / `provider probe`。

Chat Completions-compatible 示例：

```toml
provider = "chat-completions"

[providers.chat-completions]
model = "mimo-v2.5-pro"
base_url = "https://token-plan-cn.xiaomimimo.com/v1"
api_key_env = "MY_CHAT_MODEL_API_KEY"
```

PowerShell：

```powershell
$env:MY_CHAT_MODEL_API_KEY="your-api-key"
uv run repo-harness --repl
```

`api_key_env` 的含义是"RepoHarness 应该读取哪个环境变量"。如果你的厂商使用 `ACME_API_KEY`，就把 `api_key_env` 改成 `"ACME_API_KEY"`，同时替换 `model` 和 `base_url`。

配置优先级固定为：

```text
CLI 显式参数 > process env / 项目 .env > 项目 .repo-harness.toml > 全局 config > 默认值
```

其他 provider 示例：

```toml
provider = "deepseek"
max_steps = 50

[providers.deepseek]
client = "anthropic"
model = "deepseek-v4-pro"
base_url = "https://api.deepseek.com/anthropic"
api_key_env = "DEEPSEEK_API_KEY"
```

```toml
provider = "openai"

[providers.openai]
model = "gpt-5.4"
base_url = "https://api.openai.com/v1"
api_key_env = "OPENAI_API_KEY"
```

```toml
provider = "anthropic"

[providers.anthropic]
model = "claude-sonnet-4-6"
base_url = "https://api.anthropic.com/v1"
api_key_env = "ANTHROPIC_API_KEY"
```

本地 Ollama 不需要远程 API key：

```bash
uv run repo-harness --provider ollama --model qwen3.5:4b
```

用户级全局配置文件是：

```text
%USERPROFILE%\.repo-harness\config.toml
```

Linux/macOS 对应：

```text
~/.repo-harness/config.toml
```

项目 `.env` 可放常用覆盖项：

```dotenv
REPO_HARNESS_PROVIDER=openai
REPO_HARNESS_MODEL=gpt-5.4
REPO_HARNESS_MAX_NEW_TOKENS=8192
```

临时测试也可以用 CLI 参数覆盖配置，例如：

```bash
uv run repo-harness --provider openai
uv run repo-harness --provider chat-completions --base-url https://token-plan-cn.xiaomimimo.com/v1 --model mimo-v2.5-pro
uv run repo-harness --provider anthropic
uv run repo-harness --provider deepseek
uv run repo-harness --provider ollama --model qwen3.5:4b
```

如果需要临时把厂商自己的 key 变量映射成通用变量，也可以这样做；正式项目配置仍推荐使用 `.repo-harness.toml` 的 `api_key_env`：

```powershell
$env:CHAT_COMPLETIONS_API_KEY=$env:MY_CHAT_MODEL_API_KEY
uv run repo-harness --repl --provider chat-completions --base-url https://token-plan-cn.xiaomimimo.com/v1 --model mimo-v2.5-pro
```

LiteLLM、OpenRouter、Vercel AI Gateway 这类外部 gateway 可以作为 OpenAI-compatible 或 Chat Completions-compatible endpoint 接入。RepoHarness 不要求安装这些组件；如果你已经在团队里使用它们，只需要把它们暴露出的 `base_url`、`model` 和 `api_key_env` 按上面的方式配置即可。

默认 `max_steps` 为 50。`max_new_tokens` 会按 provider 推断，除非通过 CLI、环境变量或配置文件显式指定。

## 工具、安全和运行模式

RepoHarness 的工具执行统一经过 core executor、permission gate、tool policy 和 sandbox：

- `approval_policy="ask"` 对同一 risky tool 只触发一次审批。
- shell 普通搜索/读取会被拦截，鼓励使用结构化 `read_file` / `search`。
- 修改既有文件前需要 fresh read；重复工具调用会进入 guard。
- 多 tool-call 按模型输出顺序执行，partial failure 会进入 trace。
- `read_only` 模式下不执行任何 shell 命令，`excluded_commands` 在该模式下不提供豁免（[ADR-007](docs/decisions/007-read-only-不再有豁免.md)）。豁免只在 `best_effort` 下生效，那个模式本就不承诺隔离。
- Sandbox hardening（v7）：`read_only` 直接阻止 `run_shell`、关闭 `.env` 覆盖与 fail-open 回退，命令执行边界在 `auto_issue_fix` / `cli` / `tool_policy` / `workspace` / `context_manager` 统一收敛（见 [ADR-007](docs/decisions/007-read-only-不再有豁免.md)）。
- Token 估算支持 CJK 文本感知（中文字符约 1.5 token/字，ASCII 约 0.25 token/字符）。

Sandbox 支持：

```text
off | best_effort | read_only | required
```

示例：

```bash
uv run repo-harness --sandbox read_only
uv run repo-harness --sandbox required --sandbox-backend bubblewrap
```

## REPL 和工作流能力

REPL 基于 `rich` 库提供增强的终端交互体验：

- 工具调用实时显示（蓝色边框卡片 + 参数摘要）
- AI 回复 Markdown 渲染（代码块语法高亮、列表、粗体）
- `/help` 用表格显示命令列表，`/usage` 用表格显示 token 统计
- 错误用红色面板显示，状态栏显示 session/mode/steps 信息

常用 REPL 命令：

- `/help`：查看命令。
- `/plan <topic>`、`/plan-exit`、`/mode`：进入/退出 plan mode。
- `/usage`、`/model [name]`、`/history`、`/context`、`/compact`、`/working-memory`：查看运行状态。
- `/skills`、`/skill <name> [args]`：发现并调用 skills。
- `/auto-issue-fix [args]`：进入 Auto Issue Fix；在普通 REPL 中不带参数会启动引导式输入，显式加 `--dry-run` 才只生成预演证据。
- `/agents`、`/subagent explore <task>`、`/subagent worker --scope <path> <task>`：启动受限 worker。
- `/memory review`：审核长期记忆候选。
- `/memory organize`：整理候选事实，只进入 Review Queue。
- `/memory_explain <query>`：查看记忆检索解释链路。
- `/memory_pack` 或 `/memory-pack`：打开 memory pack 菜单。

## Skills

RepoHarness 会发现：

```text
skills/<name>/SKILL.md
.repo-harness/skills/<name>/SKILL.md
```

同时兼容 Claude Code Skill 格式，自动从 `~/.claude/skills/` 发现并加载 SKILL.md 文件。Claude Code 的工具名称会自动映射到 RepoHarness 等价物（`Read` → `read_file`，`Bash` → `run_shell` 等）。

Skill frontmatter 支持常见 YAML list，例如：

```yaml
---
name: inspect
allowed_tools:
  - read_file
  - search
paths:
  - src/
---
```

Claude Code 格式的 Skill 也完全兼容：

```yaml
---
name: humanizer
description: Remove AI writing patterns
allowed-tools: Read, Write, Edit, Grep
---
Your prompt here using $ARGUMENTS.
```

`allowed_tools` 会同时影响 prompt 中展示的工具列表和实际 permission gate。skill 可提供 prompt、参数替换、fork/model override 和事件记录，但不能绕过 Review Queue 写 durable memory。

## Workers

Worker 是 session-scoped 子任务：

- Explore worker 默认只读。
- Write worker 必须指定 `write_scope`。
- 支持后台生命周期、continue、stop、shutdown、running send guard、notifications 和 worker artifacts。
- Worker 继承 provider config、tool policy、sandbox 和 memory governance。

示例：

```text
/subagent explore inspect the routing layer
/subagent worker --scope src,tests add targeted tests for config precedence
/agents
```

## Auto Issue Fix 真实执行与 dry-run 预演

Auto Issue Fix 将 GitHub issue、隔离工作区、RepoHarness 修复 turn、测试验证、自动审查门、证据包和 draft PR 串成一条可复盘的维护链路。它强调的不是"自动制造 PR"，而是在真实仓库中保留授权、审查、阻断和交接边界。

`repo-harness auto-issue-fix` 是本版本的重要能力更新。默认不传 `--dry-run` 时进入真实执行：读取 GitHub issue、隔离 clone、创建分支、调用 RepoHarness 修复、运行测试、执行自动审查门、commit、push，并创建 draft PR。传入 `--dry-run` 时只生成预演证据，不执行 GitHub 副作用。

```bash
repo-harness auto-issue-fix --repo owner/name --issue 123 --mode draft-auto --test-command "python -m pytest -q" --confirm-maintainer-access
repo-harness auto-issue-fix --repo owner/name --issue 123 --dry-run
repo-harness auto-issue-fix --repo owner/name --issue 123 --mode draft-auto --dry-run
```

REPL 也可以直接进入 Auto Issue Fix：

```text
/auto-issue-fix
/auto-issue-fix --repo owner/name --issue 123
/auto-issue-fix --repo owner/name --issue 123 --mode draft-auto --confirm-maintainer-access
/auto-issue-fix --repo owner/name --issue 123 --dry-run
```

推荐在普通 REPL 中直接输入 `/auto-issue-fix` 使用引导式流程：RepoHarness 会依次询问模式、仓库、issue 编号和可选测试命令。默认模式是 `review-gated` 真实执行；输入 `dry-run` 才只生成预演证据，输入 `draft-auto` 才进入草稿 PR 自动化模式。仓库留空会进入全局 discovery，从候选仓库中筛选 issue；输入仓库但 issue 留空，会在该仓库内筛选候选 issue。

默认模式是 `review-gated`，也是推荐模式；`draft-auto` 必须显式选择。两种模式都必须经过自动审查门，区别只是：`review-gated` 在自动审查通过后仍由人确认关键节点，`draft-auto` 在自动审查通过后减少人工暂停；任何 `block` verdict 都会停止运行并生成 fallback 证据。无论使用哪种模式，输出的 patch、测试结果和 PR 描述都必须由人进行严格 review 和验证后再交给上游维护者。

Auto Issue Fix 主要面向用户解决自己维护、或明确拥有维护/贡献权限的仓库中的 issue。它的目标是负责任地高效解决清晰、可验证的问题，而不是批量制造 PR。RepoHarness 只生成候选 patch、测试日志、证据包和 PR 描述草稿；使用者必须对最终 review、验证、提交、合并和发布承担责任。默认 PR 描述使用维护者友好的六段式模板：`Summary`、`Related Issue`、`What Changed`、`Validation`、`Scope and Risk`、`Maintainer Notes`。本地工具链、模型、实验记录、trace 和 evidence 细节保留在本地证据目录，默认不写入提交给上游的 `pr-body.md`。维护者信任审查门会检查公开 PR title、body、commit message 和 branch，发现工具实验说明、敏感路径、secret 或越权措辞时会阻断发布。

真实执行默认创建 draft PR，不会自动标记 ready-for-review。默认 GitHub 接入使用本机 `gh` CLI 认证；默认测试仍使用 mocked backend，不在普通 CI 中创建真实 fork 或 PR。

每次运行会生成 `.repo-harness/auto-issue-fix/<run_id>/` 或 `--evidence-dir` 指定目录，标准文件为：

- `run-record.md`
- `pr-body.md`
- `formal-report-summary.md`
- `run-record.json`
- `pr-ready-fallback.md`，仅在失败或阻断时生成
- `issue.json`
- `baseline-repro.log`
- `fix-run.log`
- `test-after-fix.log`
- `git-diff.patch`
- `pr-url.txt`，仅成功创建 PR 时生成
- `reviews/review-<stage>.json`
- `reviews/review-<stage>.md`
- `decision-log.jsonl`
- `checkpoint.json`

报告默认使用 `<workspace>`、`<repo>`、`<evidence_dir>` 等占位符，并脱敏 API key、GitHub token、cookie 和 secret-shaped 内容。只有显式传入 `--include-local-paths` 时才会保留本地绝对路径。

## Evidence 和发布验收

RepoHarness 提供两类默认不需要 live API key 的验收：

- `RunEvidence`：通过 public CLI、scripted provider 和隔离 workspace 验证 changed file、report、trace、session events 和 state dir。
- business dogfood：默认 fake/scripted provider，覆盖 `order_pricing_bugfix`、`release_readiness_review`、`incident_resume_fix`。

Live business dogfood 必须显式 opt-in：

```powershell
$env:REPO_HARNESS_RUN_LIVE_BUSINESS_DOGFOOD="1"
```

常用维护验证：

```powershell
uv run pytest tests -q --basetemp C:\tmp\rh-test
uv run ruff check .
git diff --check
```

## Memory Pack 和可解释记忆

Memory Pack 支持导出、导入、检查和验证：

```bash
repo-harness memory export --preset safe-transfer --output memory-pack.zip
repo-harness memory inspect memory-pack.zip
repo-harness memory validate memory-pack.zip
repo-harness memory import memory-pack.zip
```

三种常用 preset：

- `safe-transfer`：只导出 accepted durable memory。
- `continue-work`：保留继续工作需要的上下文快照。
- `full-recovery`：包含更完整恢复材料，使用前应确认隐私边界。

Pending review queue 不进入 prompt memory、不参与 `/memory_explain`，也不会被 `safe-transfer` 导出。

运行工件会保留 prompts、tool outputs、local paths、reports 和 traces，方便审计 memory pack 内容来源。

记忆系统的审计字段和只读入口：

- `/memory self_iteration`：只读查看最近一次自整理，不会触发 compaction，也不会自动写 durable topics。
- `episodic_compactions`：记录 episodic notes 压缩。
- `durable_review_queued`：记录本轮进入 Review Queue 的长期事实候选。
- `self_iteration_review_queued`：记录自动整理送审候选。
- `self_iteration_rejections`：记录自动整理拒绝项。
- `.repo-harness/memory/review-queue.jsonl`：Review Queue 文件。
- `durable-review-queue-v1`：Review Queue schema。
- Pending queue：待审队列，不进入 prompt memory、`/memory_explain` 或 `safe-transfer`。
- `score_breakdown` 与 `selected_explanations`：Explainable Retrieval 的解释字段。

RepoHarness 记忆系统继续以"可迁移、可审核、可解释"为核心。

## 项目文档

**入门**

- [新手指南](docs/getting-started.md) — 从安装到跑通第一个任务
- [架构概览](docs/architecture/agent-harness-v1-overview.md)

**设计与规范**

- [整体方案](docs/spec/整体方案.md) — 痛点、设计取舍、架构、实现要点
- [工程规范](docs/spec/工程规范.md) — 质量门禁、测试规范、安全边界、迭代纪律
- [决策记录（ADR）](docs/decisions/README.md) — 为什么这么做，以及后来证明对不对
- [交付文档](docs/delivery/README.md) — 本轮优化的完整记录、测试资料与后续路线图

**功能方案**

- [Auto Issue Fix 产品方案](docs/auto-issue-fix-product-plan.md)
- [Auto Issue Fix 实现计划](docs/auto-issue-fix-implementation-plan.md)

**维护者**

- [更新日志](docs/maintainer-prep/changelog-draft.md)
- [维护者文档入口](docs/maintainer-prep/README.md)
- [Review Pack](docs/review-pack/README.md)

## 工程约定

三条长期生效的约束，来自一次技术债治理的复盘（完整背景见 [ADR-001](docs/decisions/001-放弃-codex-分支从-main-重建.md)）：

| 约定 | 含义 |
|---|---|
| [ADR-002](docs/decisions/002-安全边界用开关而非删除实现.md) | 安全边界用配置开关表达，**不删除实现**。删掉的能力找不回来，关掉的随时能开 |
| [ADR-003](docs/decisions/003-测试只测行为.md) | 测试断言行为，不断言行数、文档措辞或文件形状。会 skip 的测试等于没测 |
| [ADR-006](docs/decisions/006-交付数字必须可复现.md) | 文档里的每个数字都要能由一条命令复算 |

代码质量门禁：

```bash
uv run ruff check .        # 规则集在 pyproject.toml 显式声明，预期 0 error
uv run pytest tests/ -q    # 预期全绿
python scripts/measure.py  # 产出所有交付文档引用的量化指标
```
