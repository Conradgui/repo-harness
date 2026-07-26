# RepoHarness 新手指南

这份指南面向第一次使用 RepoHarness 的用户，也给维护者提供一条从安装到验收的最短路径。

RepoHarness 是一个面向本地仓库的可治理 coding-agent runtime。Auto Issue Fix 是它的一个重要的完整工作流。它的公开入口是：

- CLI：`repo-harness`
- 模块：`python -m repo_harness`
- 包名：`repo_harness`
- 本地状态目录：`.repo-harness/`

RepoHarness 不使用旧品牌入口，不恢复旧状态目录或旧配置文件。长期记忆只能走 Review Queue：

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

## 1. 安装和自检

进入项目根目录，确认能看到 `pyproject.toml` 和 `repo_harness/`：

```bash
uv sync
uv run python -m repo_harness --help
```

Windows PowerShell：

```powershell
uv sync
uv run python -m repo_harness --help
```

Windows CMD：

```bat
uv sync
uv run python -m repo_harness --help
```

如果看到 `No module named repo_harness`，通常是当前目录不对，或者没有执行 `uv sync` / `pip install -e .`。

## 2. 配置 provider

如果你手上已经有模型厂商给的 API key、模型名和 base URL，按这个顺序配置：

1. 看厂商文档里的 endpoint 路径。
2. 如果不确定 provider，先用 `provider probe` 根据 endpoint 或已知厂商根路径推断。
3. 把 API key 放进环境变量。
4. 在 `.repo-harness.toml` 中写 `provider`、`model`、`base_url`、`api_key_env`。
5. 用 `provider doctor` 检查配置。
6. 启动 `uv run repo-harness --repl`。

RepoHarness 支持五类 provider：

- `openai`：OpenAI-compatible Responses API；厂商文档路径是 `/v1/responses` 时使用。
- `chat-completions`：Chat Completions-compatible API；厂商文档路径是 `/v1/chat/completions` 时使用。
- `anthropic`：Anthropic-compatible Messages API；厂商文档路径是 Anthropic `/messages` 时使用。
- `deepseek`：DeepSeek 一等 provider，默认走 Anthropic-compatible client。
- `ollama`：本地 Ollama。

配置文件里的 `base_url` 只填到厂商给出的版本根路径，例如 `https://example.com/v1`。不要在 `.repo-harness.toml` 中手动把 `/responses`、`/chat/completions` 或 `/messages` 追加进去；RepoHarness 会根据 provider 自动选择具体请求路径。`provider setup` / `provider probe` 命令可以接收完整 endpoint 路径，并在写入配置时自动剥离成版本根路径。

配置优先级：

```text
CLI 显式参数 > process env / 项目 .env > 项目 .repo-harness.toml > 全局 config > 默认值
```

也可以用内置向导生成和检查配置：

```bash
repo-harness provider probe --base-url https://<vendor-host>/v1 --model <model> --api-key-env MY_MODEL_API_KEY
repo-harness provider probe --base-url https://<vendor-host>/v1 --model <model> --api-key-env MY_MODEL_API_KEY --write
repo-harness provider probe --base-url https://<vendor-host>/v1 --model <model> --api-key-env MY_MODEL_API_KEY --smoke
repo-harness provider setup --base-url https://<vendor-host>/v1/chat/completions --model <model> --api-key-env MY_MODEL_API_KEY
repo-harness provider doctor
repo-harness provider doctor --smoke
```

`provider probe` 默认不发送模型请求，只根据 endpoint 后缀或已知厂商根路径推断 provider；只有加 `--smoke` 或 `--allow-live-probe` 才会发送一次真实最小模型请求，可能产生计费、日志或 rate limit。默认不写文件，只有加 `--write` 才合并更新 `.repo-harness.toml`。`provider setup` 不写入 API key 值，只保存环境变量名；如果 `.repo-harness.toml` 已存在，它会更新 provider 配置并保留 `max_steps`、`[sandbox]` 和其他 provider section。`provider doctor` 不打印 secret，只告诉你配置是否可读、key 是否存在，以及 401/404/429 等常见错误的含义。

如果只给一个未知厂商的版本根路径，例如 `https://models.example.com/v1`，RepoHarness 无法可靠判断协议；这时请传 `--provider`，或把厂商文档里的完整 endpoint 路径交给 `provider setup` / `provider probe`。

### 2.1 OpenAI Responses-compatible

如果厂商文档写的是 `/v1/responses`，使用 `openai` provider：

```toml
provider = "openai"

[providers.openai]
model = "gpt-5.4"
base_url = "https://api.openai.com/v1"
api_key_env = "OPENAI_API_KEY"
```

macOS / Linux：

```bash
export OPENAI_API_KEY="your-api-key"
uv run repo-harness --repl
```

PowerShell：

```powershell
$env:OPENAI_API_KEY="your-api-key"
uv run repo-harness --repl
```

### 2.2 Chat Completions-compatible

如果厂商文档写的是 `/v1/chat/completions`，使用 `chat-completions` provider。很多国产模型虽然写着 OpenAI-compatible，实际兼容的是 Chat Completions 路径，不要复用 `openai` Responses provider。

MiMo 只是一个示例：

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

国产或第三方 Chat Completions-compatible 模型的通用模板如下，把 `model`、`base_url` 和 `api_key_env` 替换成厂商文档里的值：

```toml
provider = "chat-completions"

[providers.chat-completions]
model = "<vendor-model-name>"
base_url = "https://<vendor-host>/v1"
api_key_env = "<VENDOR_API_KEY_ENV>"
```

`chat-completions` 默认按以下顺序读取 API key：

```text
api_key_env from config, if set
REPO_HARNESS_CHAT_COMPLETIONS_API_KEY
REPO_HARNESS_API_KEY
CHAT_COMPLETIONS_API_KEY
OPENAI_API_KEY
```

如果厂商使用自己的环境变量名，推荐在 `.repo-harness.toml` 中用 `api_key_env` 明确指定。临时测试时，也可以把厂商 key 映射成通用变量：

```powershell
$env:CHAT_COMPLETIONS_API_KEY=$env:MY_CHAT_MODEL_API_KEY
uv run repo-harness --repl --provider chat-completions --base-url https://token-plan-cn.xiaomimimo.com/v1 --model mimo-v2.5-pro
```

P2 实测能跑通，是因为当时使用了临时脚本：脚本直接读取厂商 key 环境变量，并自己调用 `base_url + "/chat/completions"`。正式 REPL 走 RepoHarness provider 配置链路，所以必须通过 `api_key_env` 或通用环境变量告诉 RepoHarness 读哪个 key。

### 2.3 Anthropic-compatible

如果厂商文档写的是 Anthropic `/messages`，使用 `anthropic` provider：

```toml
provider = "anthropic"

[providers.anthropic]
model = "claude-sonnet-4-6"
base_url = "https://api.anthropic.com/v1"
api_key_env = "ANTHROPIC_API_KEY"
```

macOS / Linux：

```bash
export ANTHROPIC_API_KEY="your-api-key"
uv run repo-harness --repl
```

PowerShell：

```powershell
$env:ANTHROPIC_API_KEY="your-api-key"
uv run repo-harness --repl
```

### 2.4 DeepSeek

DeepSeek 是一等 provider，底层使用 Anthropic-compatible client：

```toml
provider = "deepseek"

[providers.deepseek]
client = "anthropic"
model = "deepseek-v4-pro"
base_url = "https://api.deepseek.com/anthropic"
api_key_env = "DEEPSEEK_API_KEY"
```

```bash
export DEEPSEEK_API_KEY="your-api-key"
uv run repo-harness --repl
```

PowerShell：

```powershell
$env:DEEPSEEK_API_KEY="your-api-key"
uv run repo-harness --repl
```

### 2.5 Ollama

```bash
ollama serve
ollama pull qwen3.5:4b
uv run repo-harness --provider ollama --model qwen3.5:4b
```

### 2.6 外部 gateway

LiteLLM、OpenRouter、Vercel AI Gateway 这类组件适合做团队级 provider gateway、统一鉴权、路由或成本治理。RepoHarness 不把它们作为核心依赖；如果你已经使用这些 gateway，只需要把它们暴露出的 endpoint 当成普通 provider 配置。

例如 gateway 暴露 Chat Completions-compatible endpoint：

```toml
provider = "chat-completions"

[providers.chat-completions]
model = "<gateway-model-name>"
base_url = "https://<gateway-host>/v1"
api_key_env = "GATEWAY_API_KEY"
```

如果 gateway 暴露 Responses-compatible endpoint，则把 `provider` 改为 `openai`。Auto Issue Fix 默认仍使用显式 provider，不会在运行中自动切换模型；这样 evidence 能清楚记录本次修复到底由哪个 provider 和模型驱动。

### 2.7 常见错误

- HTTP 404：通常是 provider 和 endpoint 不匹配。例如把只支持 `/chat/completions` 的模型配置成 `openai` provider，RepoHarness 会请求 `/responses`，就可能返回 404。
- HTTP 401：通常是 API key 没读到、读到了旧 key，或者 key 本身无效。优先检查 `.repo-harness.toml` 的 `api_key_env` 是否等于你实际设置的环境变量名。
- 不确定该选哪个 provider：先运行 `repo-harness provider probe --base-url <base-url> --model <model> --api-key-env <ENV_NAME>`，再看厂商文档里的完整路径，不要只看 “OpenAI-compatible” 这个营销描述。

RepoHarness 每次运行会把 report、trace、task state 等工件写入 `.repo-harness/runs/<run_id>/`。

## 3. 配置文件

项目级 `.repo-harness.toml`：

```toml
provider = "deepseek"
max_steps = 50

[providers.deepseek]
client = "anthropic"
model = "deepseek-v4-pro"
base_url = "https://api.deepseek.com/anthropic"
api_key_env = "DEEPSEEK_API_KEY"

[providers.chat-completions]
model = "mimo-v2.5-pro"
base_url = "https://token-plan-cn.xiaomimimo.com/v1"
api_key_env = "MY_CHAT_MODEL_API_KEY"

[sandbox]
mode = "best_effort"
backend = "native"
```

用户级全局配置：

```text
%USERPROFILE%\.repo-harness\config.toml
```

项目 `.env` 可覆盖环境项：

```dotenv
REPO_HARNESS_PROVIDER=openai
REPO_HARNESS_MODEL=gpt-5.4
REPO_HARNESS_MAX_STEPS=50
REPO_HARNESS_MAX_NEW_TOKENS=8192
```

默认 `max_steps` 是 50；`max_new_tokens` 会按 provider 推断。

## 4. 运行任务

进入交互模式：

```bash
uv run repo-harness
```

指定目标仓库：

```bash
uv run repo-harness --cwd /path/to/repo
```

一次性任务：

```bash
uv run repo-harness "read the failing tests and suggest a focused fix"
```

只看帮助不需要 API key：

```bash
uv run python -m repo_harness --help
```

Mock/no-live-key 验收可直接跑测试：

```bash
uv run pytest tests/test_provider_config_acceptance.py tests/test_real_session_acceptance.py -q
```

这些测试会使用 mocked provider / scripted provider，不需要真实 API key。

## 5. REPL 常用命令

- `/help`：命令列表。
- `/plan <topic>`：进入 plan mode，只允许读和计划相关工具。
- `/plan-exit`：退出 plan mode。
- `/usage`：查看 token / context 使用情况。
- `/model [name]`：查看或临时切换当前模型，不写配置文件。
- `/history`、`/context`、`/compact`、`/working-memory`：查看或整理上下文。
- `/skills`、`/skill <name> [args]`：使用 skills。
- `/agents`、`/subagent explore <task>`、`/subagent worker --scope <path> <task>`：管理 worker。
- `/memory review`：审核长期记忆候选。
- `/memory organize`：整理候选事实，只进入 Review Queue。
- `/memory_explain <query>`：解释记忆检索结果。
- `/memory_pack`：打开 memory pack 菜单。

## 6. Sandbox

Sandbox 模式：

```text
off | best_effort | read_only | required
```

示例：

```bash
uv run repo-harness --sandbox read_only
uv run repo-harness --sandbox required --sandbox-backend bubblewrap
```

`required` 模式在后端不可用时 fail closed。Windows fallback 会写入不可用 metadata，而不是伪装为完整隔离。

`read_only` 模式下不执行任何 shell 命令，`excluded_commands` 在该模式下不再提供豁免（见 ADR-007）。

## 7. Skills

Skill 文件位置：

```text
skills/<name>/SKILL.md
.repo-harness/skills/<name>/SKILL.md
```

同时兼容 Claude Code Skill 格式，自动从 `~/.claude/skills/` 发现并加载。Claude Code 工具名称自动映射：

| Claude Code | RepoHarness |
| --- | --- |
| `Read` | `read_file` |
| `Write` | `write_file` |
| `Edit` | `patch_file` |
| `Bash` | `run_shell` |
| `Glob` | `list_files` |
| `Grep` | `search` |

示例（RepoHarness 格式）：

```markdown
---
name: inspect-tests
allowed_tools:
  - read_file
  - search
paths:
  - tests/
---

Read the relevant tests and summarize the smallest useful fix.
```

示例（Claude Code 格式，同样兼容）：

```markdown
---
name: humanizer
description: Remove AI writing patterns
allowed-tools: Read, Write, Edit, Grep
---

Humanize $ARGUMENTS.
```

`allowed_tools` 会刷新 prompt 工具列表，也会限制实际工具执行。

## 8. Workers

Explore worker 适合只读调查：

```text
/subagent explore inspect the auth flow
```

Write worker 必须声明写入范围：

```text
/subagent worker --scope src,tests implement the config test fix
```

Worker 支持后台生命周期、continue、stop、shutdown、running send guard、notifications 和 artifact 汇总。

## 9. Evidence 和 dogfood

默认 evidence 不需要 live provider：

```bash
uv run python -m repo_harness --help
uv run pytest tests/test_run_evidence.py tests/test_business_scenario_dogfood.py -q
```

Business dogfood 默认 fake/scripted provider，场景为：

- `order_pricing_bugfix`
- `release_readiness_review`
- `incident_resume_fix`

Live dogfood 必须显式 opt-in：

```powershell
$env:REPO_HARNESS_RUN_LIVE_BUSINESS_DOGFOOD="1"
uv run python scripts/run_business_scenario_dogfood.py --live
```

## 10. 常见问题

**命令找不到 `repo-harness`**

先执行 `uv sync`，或使用模块入口：

```bash
uv run python -m repo_harness --help
```

### 模型请求失败

检查 provider、base URL、API key 环境变量和 `.repo-harness.toml`。优先用 `--provider`、`--model`、`--base-url` 做临时覆盖。

### 工具被拒绝

查看当前 approval、sandbox、tool profile 和 plan mode。写文件前先读文件；搜索应使用 `search`，不要用 shell 做普通搜索。

### 记忆没有进入长期 topics

这是预期行为。候选必须先进入 Review Queue，再通过 `/memory review` accept/edit。

相关只读和审计入口：

- `/memory self_iteration`：只读命令，不会触发 compaction，也不会自动写 durable topics。
- `/memory_explain <query>`
- `.repo-harness/memory/review-queue.jsonl`
- `durable-review-queue-v1`
- `durable_review_queued`
- `episodic_compactions`
- `self_iteration_review_queued`
- `self_iteration_rejections`
- Pending queue
- `safe-transfer`
- `score_breakdown`
- `selected_explanations`

Memory Pack 的 `safe-transfer`、`continue-work`、`full-recovery` 分别服务可迁移、可审核、可解释的恢复场景。运行工件中的 prompts、tool outputs、local paths、reports 和 traces 用于复盘。

## 11. 项目背景和读者

RepoHarness 曾有 v2.0 历史实验结果，用来验证本地 coding agent 在仓库任务中的可复现性。当前最终版面向实际开发者、维护者和 AI 产品经理：它不仅展示模型调用，也展示 provider 配置、工具治理、运行证据和记忆治理如何组合成一个可落地的 Agent 产品。

## 12. 维护验证

```powershell
uv run pytest tests -q --basetemp C:\tmp\rh-test
uv run ruff check .
git diff --check
```

## Auto Issue Fix 真实执行与 dry-run 预演

Auto Issue Fix 是本版本的重要能力更新。默认不传 `--dry-run` 时，它会读取 GitHub issue、隔离 clone、创建分支、调用 RepoHarness 修复、运行测试、执行自动审查门，并在通过后创建 draft PR。传入 `--dry-run` 时只生成预演证据，不执行 GitHub 副作用。

```bash
uv run repo-harness auto-issue-fix --repo owner/name --issue 123 --mode draft-auto --test-command "python -m pytest -q" --confirm-maintainer-access
uv run repo-harness auto-issue-fix --repo owner/name --issue 123 --dry-run
```

如需指定证据目录：

```bash
uv run repo-harness auto-issue-fix --repo owner/name --issue 123 --dry-run --evidence-dir <evidence_dir>
```

REPL 中也可以使用：

```text
/auto-issue-fix
/auto-issue-fix --repo owner/name --issue 123
/auto-issue-fix --repo owner/name --issue 123 --mode draft-auto --confirm-maintainer-access
/auto-issue-fix --repo owner/name --issue 123 --dry-run
```

在普通 REPL 中只输入 `/auto-issue-fix` 会进入引导式流程，依次询问模式、仓库、issue 编号和可选测试命令。默认是 `review-gated` 真实执行；输入 `dry-run` 才只生成预演证据，输入 `draft-auto` 才进入草稿 PR 自动化模式。仓库留空会进入全局 discovery，从候选仓库中筛选 issue；输入仓库但 issue 留空，会在该仓库内筛选候选 issue。

标准证据文件：

- `run-record.md`：完整审计记录。
- `pr-body.md`：提交给上游维护者的 PR 描述草稿。
- `formal-report-summary.md`：面试/作品集讲述版。
- `run-record.json`：机器可读运行摘要。
- `pr-ready-fallback.md`：失败或阻断时生成的 PR-ready fallback。
- `issue.json`：GitHub issue 快照。
- `baseline-repro.log`：修复前验证命令输出。
- `fix-run.log`：RepoHarness 修复 turn 输出。
- `test-after-fix.log`：修复后验证命令输出。
- `git-diff.patch`：提交前 diff。
- `pr-url.txt`：成功创建 draft PR 后记录 URL。
- `reviews/review-<stage>.json` / `reviews/review-<stage>.md`：自动审查门结果。
- `decision-log.jsonl`：阶段性决策流水。
- `checkpoint.json`：恢复和排障入口。

默认模式是 `review-gated`。`draft-auto` 必须显式选择，并会输出风险提示：

```bash
uv run repo-harness auto-issue-fix --repo owner/name --issue 123 --mode draft-auto --dry-run
```

两种模式都必须经过自动审查门。`review-gated` 是“自动审查 + 人工确认”，也是推荐的日常使用方式；`draft-auto` 是“自动审查 + 无人工暂停”。如果任何审查门给出 `block`，运行会停止并写入 fallback 证据。无论选择哪种模式，最终 patch、测试日志和 PR 描述都需要人工严格 review 和验证，确认质量、范围和语气都适合提交给上游维护者。

默认 `pr-body.md` 使用维护者友好的六段式模板：`Summary`、`Related Issue`、`What Changed`、`Validation`、`Scope and Risk`、`Maintainer Notes`。本地工具链、模型、实验记录、trace 和 evidence 细节只保留在本地证据目录，不默认写入公开 PR 描述。维护者信任审查门会检查公开 PR title、body、commit message 和 branch；如果发现工具实验说明、敏感路径、secret 或容易被误解的自动化措辞，会阻断发布并生成 fallback 证据。

报告默认使用 `<workspace>`、`<repo>`、`<evidence_dir>` 等占位符，并脱敏 token、cookie、API key 和 secret-shaped 内容。只有明确需要本机排障时才使用 `--include-local-paths`；该选项会把本地绝对路径写进证据，分享前需要复核。

真实执行默认创建 draft PR，不会自动标记 ready-for-review。默认 GitHub 接入使用本机 `gh` CLI 认证；普通测试使用 mocked backend，不访问真实 GitHub。
