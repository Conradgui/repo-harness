# RepoHarness 新手指南

这份指南面向第一次使用 RepoHarness 的用户，也给维护者提供一条从安装到验收的最短路径。

RepoHarness 是本地仓库里的 coding agent。它的公开入口是：

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

默认 provider 是 `openai`。支持：

- `openai`
- `anthropic`
- `deepseek`
- `ollama`

配置优先级：

```text
CLI 显式参数 > process env / 项目 .env > 项目 .repo-harness.toml > 全局 config > 默认值
```

### OpenAI-compatible

macOS / Linux：

```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_API_BASE="https://your-api.example/v1"
export OPENAI_MODEL="gpt-5.4"
uv run repo-harness --provider openai
```

PowerShell：

```powershell
$env:OPENAI_API_KEY="your-api-key"
$env:OPENAI_API_BASE="https://your-api.example/v1"
$env:OPENAI_MODEL="gpt-5.4"
uv run repo-harness --provider openai
```

### Anthropic-compatible

```bash
export ANTHROPIC_API_KEY="your-api-key"
export ANTHROPIC_API_BASE="https://your-anthropic-compatible.example/v1"
export ANTHROPIC_MODEL="claude-sonnet-4-6"
uv run repo-harness --provider anthropic
```

### DeepSeek

DeepSeek 是一等 provider，底层使用 Anthropic-compatible client：

```bash
export DEEPSEEK_API_KEY="your-api-key"
export DEEPSEEK_MODEL="deepseek-v4-pro"
uv run repo-harness --provider deepseek
```

RepoHarness 每次运行会把 report、trace、task state 等工件写入 `.repo-harness/runs/<run_id>/`。

PowerShell：

```powershell
$env:DEEPSEEK_API_KEY="your-api-key"
$env:DEEPSEEK_MODEL="deepseek-v4-pro"
uv run repo-harness --provider deepseek
```

### Ollama

```bash
ollama serve
ollama pull qwen3.5:4b
uv run repo-harness --provider ollama --model qwen3.5:4b
```

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

## 7. Skills

Skill 文件位置：

```text
skills/<name>/SKILL.md
.repo-harness/skills/<name>/SKILL.md
```

示例：

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

## 9. TUI

安装 Textual extra 后启动：

```bash
uv run --extra tui repo-harness --tui
```

TUI 和 REPL 共用同一 runtime，slash completion、normal turn、ask_user 和 worker notification 都会走同一套事件与权限路径。

## 10. Evidence 和 dogfood

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

## 11. 常见问题

**命令找不到 `repo-harness`**

先执行 `uv sync`，或使用模块入口：

```bash
uv run python -m repo_harness --help
```

**模型请求失败**

检查 provider、base URL、API key 环境变量和 `.repo-harness.toml`。优先用 `--provider`、`--model`、`--base-url` 做临时覆盖。

**工具被拒绝**

查看当前 approval、sandbox、tool profile 和 plan mode。写文件前先读文件；搜索应使用 `search`，不要用 shell 做普通搜索。

**记忆没有进入长期 topics**

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

## 12. 项目背景和读者

RepoHarness 曾有 v2.0 历史实验结果，用来验证本地 coding agent 在仓库任务中的可复现性。当前最终版面向实际开发者、维护者和 AI 产品经理：它不仅展示模型调用，也展示 provider 配置、工具治理、运行证据和记忆治理如何组合成一个可落地的 Agent 产品。

## 13. 维护验证

```powershell
uv run pytest tests -q --basetemp C:\tmp\rh-test
uv run ruff check .
git diff --check
uv run --extra tui pytest tests/test_tui.py -q
```
