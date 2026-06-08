# RepoHarness

> **v0.2.0** | Python 3.10+ | MIT License

RepoHarness 是一个运行在本地仓库里的轻量 coding agent。它通过受约束工具读取文件、修改文件、运行命令，并把会话、运行工件、记忆和审计信息保存在 `.repo-harness/` 下。

RepoHarness 面向需要在本地仓库中可控使用 AI agent 的工程场景：把上下文治理、权限控制、记忆审查、证据留存和 issue 修复流程放进同一套运行边界。Agent 可以执行实际工作，维护者也能持续追踪它读了什么、改了什么、为什么这么做，以及失败时留下了哪些证据。

## v6 版本迭代

v6 聚焦安全加固、稳定性提升、可观测性和多 Agent 编排能力：

| 类别 | 变更 |
| --- | --- |
| 安全加固（16 项） | 沙箱默认改为 `best_effort`；`run_shell` 危险命令黑名单；bubblewrap 加 `--unshare-net` 网络隔离；`search` 防 ReDoS（`--fixed-strings` + 长度限制）；evaluator verifier 命令白名单；secret 脱敏增强（regex 后处理 sk-/AKIA/JWT 等）；session 持久化前自动脱敏；PATH 清理；TOCTOU 竞态修复；`.env` 加入 `.gitignore`；恶意 TOML 配置加载警告；路径逃逸改用 `Path.is_relative_to()`；依赖版本上限 |
| 稳定性提升（27 项） | 所有工具层加 `OSError`/`TimeoutExpired` 错误捕获；`SessionStore`/`RunStore`/`DurableMemoryStore` 原子写入；memory 文件损坏检测；context window 预检自动压缩；重复调用守卫改为滑动窗口；`WorkerManager` TOCTOU 修复 + worker 超时；history item 安全访问；错误信息统一英文；死代码清理 |
| 可观测性 | 新增 `/metrics` 命令：工具调用统计（成功率/平均耗时）、循环调用检测、热路径分析、失败率突增告警、session token 消耗估算；metrics 快照自动保存到 `.repo-harness/metrics/` |
| 多 Agent 编排 | `WorkerManager` 新增 `parallel()`（并行执行）、`pipeline()`（串行输出传递）、`dag()`（依赖关系并行）、`post_message()`/`read_messages()`（worker 间消息队列）；auto-issue-fix 重构为 5 stage 流水线 + 失败重试 |
| Auto Issue Fix 重构 | 流程拆分为 Analyze → Clone+Baseline → Fix（可重试）→ Review → Commit+Push+PR；review gate 阻塞时不重试，仅测试失败时重试；每个 attempt 的日志独立保存 |

详细变更记录见 [changelog-draft.md](docs/maintainer-prep/changelog-draft.md)。

## v5 版本迭代

v5 聚焦上下文治理升级和代码质量提升：

| 类别 | 变更 |
| --- | --- |
| 动态 Context Budget | 根据模型 context window 自动计算预算（最高 400K 字符），替代固定 12K 限制 |
| Provider 元数据 | `ProviderRegistryEntry` 新增 `context_window` 和 `supports_native_tools` 字段 |
| 智能 recent_window | 历史窗口从固定 6 条缩放为根据预算动态调整（6/10/16/24 条） |
| 死代码清理 | 删除 3 个未使用的 compatibility shim 文件 + 2 个死方法，消除冗余 `_normalize_tool_args` |
| 补全命令建议 | `ReplFacade.suggest_commands()` 补全 8 个缺失的 slash 命令 |
| 边界测试 | 新增 12 个 `detect_context_window` / `compute_budgets` 边界测试 |

详细变更记录见 [changelog-draft.md](docs/maintainer-prep/changelog-draft.md)。

## v4 版本迭代

v4 是与 v3 同等重要的版本迭代，聚焦代码清理、安全加固、架构改进和生态兼容：

| 类别 | 变更 |
| --- | --- |
| 安全修复 | Shell `excluded_commands` metacharacter 绕过漏洞修复 |
| 死代码清理 | 删除 254 行 runtime.py 不可达代码 + 5 个重复 re-export 文件 + 490 行 TUI 死代码 |
| 架构改进 | `SessionStore` 提取为独立模块；`ReplFacade` 从 TUI 提取为独立模块 |
| Token 估算 | CJK-aware token 估算（中文字符 ~1.5 token/字，ASCII ~0.25 token/字符） |
| 路径编码 | 修复 Windows CJK 路径编码问题（`workspace.py` git 子进程使用 UTF-8） |
| REPL 增强 | 基于 `rich` 的增强 REPL：工具调用卡片、Markdown 渲染、语法高亮、状态栏 |
| 新功能 | Claude Code Skill 兼容层（`claude_code_skills.py`），支持从 `~/.claude/skills/` 发现和加载 |
| CI 增强 | Python 3.10-3.13 测试矩阵 + TUI 专属 job + 覆盖率报告 |
| 测试改进 | `conftest.py` 共享 fixtures + sandbox 安全测试扩展 |

详细变更记录见 [changelog-draft.md](docs/maintainer-prep/changelog-draft.md)。

## 产品边界

- CLI 入口是 `repo-harness`，模块入口是 `python -m repo_harness`，Python 包名是 `repo_harness`。
- 本地状态目录只使用 `.repo-harness/`。
- 长期记忆必须经过 Review Queue；`/remember`、`/memory organize`、skills、workers、evidence 和自动整理都不能直接写 durable topics。
- Memory Pack、Explainable Retrieval、Fuzzy Lexical Retrieval 和 Review Queue 是 RepoHarness 的核心优势，不因外部兼容诉求而降级。
- Auto Issue Fix v2 提供真实执行模式和 dry-run 预演：CLI/REPL 入口、issue 获取、隔离 clone、RepoHarness 修复、测试、自动审查门、draft PR、脱敏和路径普适化已落地。

## 能力概览

| 能力 | 面向的问题 | RepoHarness 的处理方式 |
| --- | --- | --- |
| 本地受控 agent runtime | Agent 需要读写仓库和运行命令，但不能失控执行。 | 统一经过 tool executor、permission gate、tool policy 和 sandbox。沙箱默认 `best_effort`，危险命令黑名单自动拦截。 |
| Provider 配置闭环 | 不同模型厂商 endpoint、协议和 key 管理容易混乱。 | 提供 provider setup / probe / doctor，并只保存环境变量名，不写入 secret。 |
| Memory governance | 长期记忆如果自动写入，会污染后续推理。 | 所有 durable memory 必须先进入 Review Queue，再由人 accept/edit。原子写入 + 损坏检测。 |
| Explainable retrieval | 记忆命中如果不可解释，很难审计。 | 保留 score breakdown 和 selected explanations，支持 `/memory_explain`。 |
| Auto Issue Fix | AI 修 issue 需要真实执行能力，也需要证据和门禁。 | 5 stage 流水线（Analyze→Clone→Fix→Review→Commit）+ 失败重试 + 自动审查门 + draft PR。 |
| 多 Agent 编排 | 复杂任务需要并行执行和依赖管理。 | `parallel()` 并行、`pipeline()` 串行传递、`dag()` 依赖关系并行、worker 间消息队列。 |
| 可观测性 | Agent 行为不可见，难以调试和优化。 | `/metrics` 命令展示工具统计、循环检测、热路径、失败率告警、token 消耗；快照自动持久化。 |
| Claude Code Skill 兼容 | 不同 agent 平台的 skill 生态割裂。 | 自动从 `~/.claude/skills/` 发现 SKILL.md，工具名称自动映射。 |
| Release evidence | 关键路径需要可复现验证。 | 通过 scripted provider、dogfood、focused tests 和 release evidence 验证关键路径。 |

长期记忆治理路径固定为：

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

完整新手流程见 [docs/getting-started.md](docs/getting-started.md)。

## 验证与证据索引

RepoHarness 的证据分两层：仓库内保留可复现的验证入口；真实 API 原始输出、面试流程图和一次性过程材料保留在本地 evidence pack，不默认提交到公开仓库。

| 证据类型 | 仓库内入口 | 用途 |
| --- | --- | --- |
| 架构图 / 运行流程 | [架构概览](docs/architecture/agent-harness-v1-overview.md)、[review pack](docs/review-pack/README.md) | 说明 CLI → runtime → model → tools → session events → evidence 的主链路，以及 Auto Issue Fix 的 5 stage 流程。 |
| 用户主要路径 | [getting started](docs/getting-started.md)、本 README 的 Auto Issue Fix 与 Memory Pack 章节 | 展示 provider onboarding、REPL、memory review、worker、Auto Issue Fix 和 evidence 生成路径。 |
| 安全与质量测试 | `tests/unit/`、`tests/test_dangerous_commands.py`、`tests/test_safety_invariants.py` | 覆盖路径逃逸、危险命令、secret 脱敏、sandbox、tool policy 和错误传播。 |
| 真实 provider 集成 | `tests/integration/test_api_integration.py` | DeepSeek / MIMO API key 存在时运行；无 key 时自动 skip，不作为 CI 默认 live 调用。 |
| Benchmark harness | `tests/benchmark/`、`tests/test_benchmark_evaluator.py` | 对比 Tool Runner 和裸模型 baseline，评分维度包括完整性、可审计性、稳定性、可控性和 UX。 |
| 本地面试证据包 | `RepoHarness-evidence-pack-<date>/02_codex_rerun_complete_evidence/` | 保存手册重跑的 phase manifests、流程图源文件、真实 API 报告、Benchmark 原始 JSON/Markdown 和面试材料；分享前需要脱敏复核。 |

Benchmark 需要显式提供本地 fixture 和 provider key，不会默认触发真实 API：

```powershell
$env:REPO_HARNESS_BENCHMARK_REPO="C:\path\to\rich"
$env:DEEPSEEK_API_KEY="<your-key>"
uv run python tests/benchmark/run_benchmark.py --provider deepseek --output-dir <evidence_dir>
```

维护者提交 PR 前推荐运行：

```bash
uv run pytest tests/test_benchmark_evaluator.py tests/test_dangerous_commands.py tests/test_worker_orchestration.py tests/unit tests/integration -q
uv run pytest -q
```

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
- `run_shell` 内置危险命令黑名单（`rm -rf /`、`curl | sh`、`shutdown`、`kill -9 -1` 等），自动拦截。
- `search` 默认使用 `--fixed-strings` 字面匹配，防止 ReDoS 攻击；pattern 长度限制 200 字符。
- 修改既有文件前需要 fresh read；重复工具调用改为滑动窗口检测（最近 5 条中出现 3 次相同调用）。
- 多 tool-call 按模型输出顺序执行，partial failure 会进入 trace。
- `excluded_commands` 使用前导空格规范化和 shell 元字符检测（`$(`、`` ` ``、`\`、`${`）防止绕过 sandbox。
- bubblewrap 沙箱默认启用 `--unshare-net` 网络隔离。
- Token 估算支持 CJK 文本感知（中文字符约 1.5 token/字，ASCII 约 0.25 token/字符）。
- Context window 预检：prompt 超限时自动压缩 history 并重建 prompt。

Sandbox 默认为 `best_effort`（有 bubblewrap 就用，没有则回退并记录警告）：

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
- `/metrics`：查看工具调用统计（成功率、平均耗时、循环检测、热路径、token 消耗），快照自动保存到 `.repo-harness/metrics/`。
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

## Workers 和编排

Worker 是 session-scoped 子任务：

- Explore worker 默认只读。
- Write worker 必须指定 `write_scope`。
- 支持后台生命周期、continue、stop、shutdown、running send guard、notifications 和 worker artifacts。
- Worker 继承 provider config、tool policy、sandbox 和 memory governance。
- Worker 默认最大 30 步，防止僵尸线程。

编排原语（通过 `WorkerManager` API 调用）：

- `parallel(tasks)`：并行执行多个 worker，等待全部完成，返回结构化结果。
- `pipeline(stages)`：串行执行，前一个输出通过 `{input}` 传给下一个；stage 失败时后续标记为 skipped。
- `dag(tasks)`：支持依赖关系的并行执行（拓扑排序 + 批次并行 + 失败阻断下游）。
- `post_message(channel, msg)` / `read_messages(channel)`：worker 间消息队列。

示例：

```text
/subagent explore inspect the routing layer
/subagent worker --scope src,tests add targeted tests for config precedence
/agents
```

## Auto Issue Fix 真实执行与 dry-run 预演

Auto Issue Fix 将 GitHub issue、隔离工作区、RepoHarness 修复 turn、测试验证、自动审查门、证据包和 draft PR 串成一条可复盘的维护链路。它强调的不是"自动制造 PR"，而是在真实仓库中保留授权、审查、阻断和交接边界。

`repo-harness auto-issue-fix` 是本版本的重要能力更新。默认不传 `--dry-run` 时进入真实执行：读取 GitHub issue、隔离 clone、创建分支、调用 RepoHarness 修复、运行测试、执行自动审查门、commit、push，并创建 draft PR。传入 `--dry-run` 时只生成预演证据，不执行 GitHub 副作用。

v6 重构为 5 stage 流水线：Analyze（issue 发现）→ Clone+Baseline（克隆 + 基线测试）→ Fix（agent 修复，可重试）→ Review（测试 + diff + 审查门）→ Commit+Push+PR。review gate 阻塞时不重试，仅测试失败时自动重试（默认最多 2 次）。每个 attempt 的日志和 patch 独立保存。

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

当前测试规模：398 passed，覆盖安全、工具、引擎、记忆、编排、auto-issue-fix、provider、skills、workers 等全部模块。

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

- [新手指南](docs/getting-started.md)
- [架构概览](docs/architecture/agent-harness-v1-overview.md)
- [更新日志](docs/maintainer-prep/changelog-draft.md)
- [Auto Issue Fix 产品方案](docs/auto-issue-fix-product-plan.md)
- [Auto Issue Fix 实现计划](docs/auto-issue-fix-implementation-plan.md)
- [维护者文档入口](docs/maintainer-prep/README.md)
- [Review Pack](docs/review-pack/README.md)
