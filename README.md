# RepoHarness

RepoHarness 是一个运行在本地仓库里的轻量 coding agent。它通过受约束工具读取文件、修改文件、运行命令，并把会话、运行工件、记忆和审计信息保存在 `.repo-harness/` 下。

当前版本已经完成 v3 能力完善收尾，并把 Auto PR 升级为同等级的重要版本能力。RepoHarness 继续保留自己的产品边界：

- CLI 入口是 `repo-harness`，模块入口是 `python -m repo_harness`，Python 包名是 `repo_harness`。
- 本地状态目录只使用 `.repo-harness/`。
- 长期记忆必须经过 Review Queue；`/remember`、`/memory organize`、skills、workers、evidence 和自动整理都不能直接写 durable topics。
- Memory Pack、Explainable Retrieval、Fuzzy Lexical Retrieval 和 Review Queue 是 RepoHarness 的核心优势，不因外部兼容诉求而降级。
- Auto PR 当前提供框架与安全预演模式：CLI/REPL 入口、标准证据包、自动审查门、脱敏和路径普适化已落地；真实 clone/fix/test/push/PR 属于下一阶段。

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

RepoHarness 支持四类 provider：

- `openai`：OpenAI-compatible Responses API，默认 provider。
- `anthropic`：Anthropic-compatible Messages API。
- `deepseek`：一等 provider，走 Anthropic-compatible client。
- `ollama`：本地 Ollama。

配置优先级固定为：

```text
CLI 显式参数 > process env / 项目 .env > 项目 .repo-harness.toml > 全局 config > 默认值
```

项目级配置文件是 `.repo-harness.toml`：

```toml
provider = "deepseek"
max_steps = 50

[providers.deepseek]
client = "anthropic"
model = "deepseek-v4-pro"
base_url = "https://api.deepseek.com/anthropic"
api_key_env = "DEEPSEEK_API_KEY"
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

常用启动示例：

```bash
uv run repo-harness --provider openai
uv run repo-harness --provider anthropic
uv run repo-harness --provider deepseek
uv run repo-harness --provider ollama --model qwen3.5:4b
```

默认 `max_steps` 为 50。`max_new_tokens` 会按 provider 推断，除非通过 CLI、环境变量或配置文件显式指定。

## 工具、安全和运行模式

RepoHarness 的工具执行统一经过 core executor、permission gate、tool policy 和 sandbox：

- `approval_policy="ask"` 对同一 risky tool 只触发一次审批。
- shell 普通搜索/读取会被拦截，鼓励使用结构化 `read_file` / `search`。
- 修改既有文件前需要 fresh read；重复工具调用会进入 guard。
- 多 tool-call 按模型输出顺序执行，partial failure 会进入 trace。

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

常用 REPL 命令：

- `/help`：查看命令。
- `/plan <topic>`、`/plan-exit`、`/mode`：进入/退出 plan mode。
- `/usage`、`/model [name]`、`/history`、`/context`、`/compact`、`/working-memory`：查看运行状态。
- `/skills`、`/skill <name> [args]`：发现并调用 skills。
- `/auto-pr [args]`：进入 Auto PR 安全预演；未提供仓库和 issue 时会生成自动发现规划证据。
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

## TUI

安装 Textual extra 后可启动 TUI：

```bash
uv run --extra tui repo-harness --tui
```

TUI 使用同一套 runtime，不是独立行为路径；slash completion、normal turn、ask_user prompt 和 worker notification 都走公共 runtime。

## Auto PR 框架与安全预演

`repo-harness auto-pr` 是本版本的重要能力更新。当前公开能力是框架与安全预演模式：生成标准证据工件、自动审查门、decision log、checkpoint、脱敏报告和路径占位符，不执行真实 clone、push 或 PR 创建。

```bash
repo-harness auto-pr --repo owner/name --issue 123 --dry-run
repo-harness auto-pr --repo owner/name --issue 123 --mode draft-auto --dry-run
```

REPL 也可以直接进入安全预演：

```text
/auto-pr
/auto-pr --repo owner/name --issue 123
/auto-pr --repo owner/name --issue 123 --mode draft-auto
```

默认模式是 `review-gated`；`draft-auto` 必须显式选择。两种模式都必须经过自动审查门，区别只是：`review-gated` 在自动审查通过后仍由人确认关键节点，`draft-auto` 在自动审查通过后减少人工暂停；任何 `block` verdict 都会停止运行并生成 fallback 证据。

当前 live issue discovery、clone/fix/test/push/PR runner 仍属于下一阶段，不应把安全预演误写成已完成的全自动 PR。

每次 dry-run 会生成 `.repo-harness/auto-pr/<run_id>/` 或 `--evidence-dir` 指定目录，标准文件为：

- `run-record.md`
- `pr-body.md`
- `formal-report-summary.md`
- `run-record.json`
- `pr-ready-fallback.md`，仅在失败或阻断时生成
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

RepoHarness 记忆系统继续以“可迁移、可审核、可解释”为核心。

## 项目文档

- [新手指南](docs/getting-started.md)
- [架构概览](docs/architecture/agent-harness-v1-overview.md)
- [Auto PR 产品方案](docs/auto-pr-product-plan.md)
- [Auto PR 实现计划](docs/auto-pr-implementation-plan.md)
- [维护者文档入口](docs/maintainer-prep/README.md)
- [Review Pack](docs/review-pack/README.md)
