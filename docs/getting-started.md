# RepoHarness 新手指南

## v3 Compat Phase 2 Workflow And UX

Phase 2 adds workflow commands on top of the Phase 1 foundation:

- `/skills` lists discovered project and local RepoHarness skills.
- `/skill <name> [args]` injects a selected skill into the current interaction as controlled prompt text.
- `todo_add`, `todo_update`, and `todo_list` keep session-scoped work status in the prompt and report.
- `/agents`, `/subagent explore <task>`, and `/subagent worker --scope <path[,path]> <task>` run bounded worker tasks.
- `--sandbox read_only`, `--sandbox best_effort`, and `[sandbox]` in `.repo-harness.toml` control shell execution.
- `--tui` opens the optional Textual TUI; `--repl` keeps the standard REPL path.

These workflow features inherit provider config, secret redaction, tool policy, and memory governance. They can create candidates or runtime artifacts, but they do not bypass:

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

## v3 Compat Phase 1 Foundation

RepoHarness can be configured with `.repo-harness.toml`. The Phase 1 foundation release supports OpenAI, Anthropic, and DeepSeek provider profiles. DeepSeek uses the Anthropic-compatible protocol.

```toml
provider = "deepseek"
max_steps = 50
max_new_tokens = 8192

[providers.deepseek]
client = "anthropic"
model = "deepseek-v4-pro"
base_url = "https://api.deepseek.com/anthropic"
api_key_env = "DEEPSEEK_API_KEY"
```

CLI arguments override environment variables, environment variables override `.repo-harness.toml`, and the file overrides code defaults. `/remember <text>` is only a Review Queue entrypoint:

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

Phase 2 will handle skills, todo ledger, worker manager, sandbox, runtime control plane layering, Textual TUI, and release evidence. Reference v3 commit: `91a7c17`; old stable reference tag: `archive-before-repoharness-rename-20260503`.

`repo-harness` 是一个运行在本地终端里的轻量 coding agent，也可以理解为一个面向代码仓库的 Agent Harness：它把模型、仓库上下文、受约束工具、审批机制、会话状态、运行工件和记忆系统组织成一个可持续工作的命令行助手。

这份指南面向三类读者：

- 第一次使用 RepoHarness 的用户：快速配置模型后端，把 CLI 跑起来。
- 新维护者：知道应该从哪条主链路理解项目。
- HR / 面试官：快速理解这个项目体现出的 AI 产品设计、Agent 架构和工程落地能力。

README 是快速入口；如果你想从“完全没用过”到“能配置、能使用、能解释 RepoHarness”，建议按本文顺序阅读。

## 5 分钟快速跑起来

先确认当前终端已经进入 RepoHarness 项目根目录。这个目录下应该能看到 `pyproject.toml` 和 `repo_harness/` 包目录。

macOS / Linux：

```bash
cd /path/to/repo-harness
uv sync
uv run python -m repo_harness --help
uv run repo-harness
```

Windows PowerShell：

```powershell
cd C:\path\to\repo-harness
uv sync
uv run python -m repo_harness --help
uv run repo-harness
```

Windows CMD：

```bat
cd /d C:\path\to\repo-harness
uv sync
uv run python -m repo_harness --help
uv run repo-harness
```

如果你在 `C:\Users\YourName` 这类非项目目录直接运行 `uv run python -m repo_harness --help`，Python 找不到当前仓库里的 `repo_harness` 包，可能会看到 `No module named repo_harness` 或 `program not found`。解决方式不是改代码，而是先进入项目根目录，或者先执行 `pip install -e .` 把包安装到当前 Python 环境。

## 三类模型后端怎么配置

RepoHarness 支持三类模型后端：Ollama、OpenAI 兼容 Responses API、Anthropic 兼容 Messages API。CLI 默认使用 `openai` provider。

### Ollama：本地模型，不需要 API Key

Ollama 适合本地试跑和离线实验。它不需要 API Key，但需要本机已经安装并启动 Ollama。

```bash
ollama serve
ollama pull qwen3.5:4b
uv run repo-harness --provider ollama --model qwen3.5:4b
```

PowerShell 和 CMD 里命令相同。注意：`ollama serve` 通常需要保持运行；可以单独开一个终端窗口运行服务，再在另一个终端启动 RepoHarness。

### OpenAI 兼容接口：默认推荐路径

RepoHarness 默认 provider 是 `openai`，默认模型是 `gpt-5.4`。如果不显式传 `--base-url`，项目会使用默认 OpenAI-compatible 服务地址。你至少需要配置 `OPENAI_API_KEY`。

macOS / Linux：

```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_API_BASE="https://your-api.example/v1"
export OPENAI_MODEL="gpt-5.4"
uv run repo-harness --provider openai
```

Windows PowerShell：

```powershell
$env:OPENAI_API_KEY="your-api-key"
$env:OPENAI_API_BASE="https://your-api.example/v1"
$env:OPENAI_MODEL="gpt-5.4"
uv run repo-harness --provider openai
```

Windows CMD：

```bat
set OPENAI_API_KEY=your-api-key
set OPENAI_API_BASE=https://your-api.example/v1
set OPENAI_MODEL=gpt-5.4
uv run repo-harness --provider openai
```

如果你只想验证 CLI 是否能启动，可以先运行 `uv run python -m repo_harness --help`。这个命令不需要 API Key。进入 `repo-harness>` 后发送真实任务时，模型请求才会需要有效密钥。

### Anthropic 兼容接口

Anthropic-compatible provider 默认模型是 `claude-sonnet-4-6`。示例中的 API 地址请替换成你实际使用的 Anthropic-compatible 服务地址。

macOS / Linux：

```bash
export ANTHROPIC_API_KEY="your-api-key"
export ANTHROPIC_API_BASE="https://your-anthropic-compatible.example/v1"
export ANTHROPIC_MODEL="claude-sonnet-4-6"
uv run repo-harness --provider anthropic
```

Windows PowerShell：

```powershell
$env:ANTHROPIC_API_KEY="your-api-key"
$env:ANTHROPIC_API_BASE="https://your-anthropic-compatible.example/v1"
$env:ANTHROPIC_MODEL="claude-sonnet-4-6"
uv run repo-harness --provider anthropic
```

Windows CMD：

```bat
set ANTHROPIC_API_KEY=your-api-key
set ANTHROPIC_API_BASE=https://your-anthropic-compatible.example/v1
set ANTHROPIC_MODEL=claude-sonnet-4-6
uv run repo-harness --provider anthropic
```

## RepoHarness 里可以输入什么

启动后你会看到 `repo-harness>`。这不是系统 shell，而是 RepoHarness 的交互式 REPL。你可以直接输入自然语言任务，也可以输入内置命令。

常用任务示例：

```text
repo-harness> inspect the test failures and propose a fix
repo-harness> read README and summarize how this project starts
repo-harness> find where run_shell validates arguments
repo-harness> update the docs for Windows PowerShell usage
```

常用内置命令：

- `/help`：查看 REPL 内置命令。
- `/memory`：查看当前会话提炼出来的工作记忆。
- `/memory review`：审核 pending durable memory 候选，确认后才写入长期记忆。
- `/memory self_iteration`：只读查看最近一次 Memory Self-Iteration 状态。
- `/memory_explain <query>`：查看 Explainable Retrieval v1 如何为某个查询选择 memory。
- `/memory_pack` 或 `/memory-pack`：打开 memory pack 菜单，用于导出、导入、检查或验证记忆包。
- `/session`：查看当前 session 文件路径。
- `/reset`：清空当前会话状态。
- `/exit` 或 `/quit`：退出 RepoHarness。

注意：在 `repo-harness>` 里输入 `cd C:\path\to\repo` 或 `uv run repo-harness`，RepoHarness 会把它当成给 agent 的自然语言任务，不会像普通终端那样直接执行。要切换目录或重新启动 RepoHarness，请先 `/exit` 回到 PowerShell / CMD / shell。

### 解释 memory 为什么被选中

当你想知道某条长期记忆为什么进入当前上下文，可以在 REPL 里输入：

```text
repo-harness> /memory_explain pytest windows shell
```

Explainable Retrieval v1 只解释当前轻量 lexical retrieval 的选择过程，不会写入或重排 memory。输出中的 `score_breakdown` 展示 tag match、keyword overlap、recency、kind 等分项信号；`source` 和 `selected_explanations` 用来说明被选中的 memory、来源 topic 或 session 来源。检索会对大小写、分隔符和 camelCase / PascalCase 做确定性归一化，例如 `memory-pack`、`memory_pack`、`MemoryPack` 和 `memory pack` 可以互相召回；它不做 edit distance、同义词表或 semantic retrieval。维护者排障时可以把 durable `source` topic slug 追踪到 `.repo-harness/memory/topics/<topic>.md`。

### 审核长期记忆候选

当你明确要求 RepoHarness 保存长期记忆时，系统会先把候选写入 `.repo-harness/memory/review-queue.jsonl`，不会立刻污染 durable topics。之后可以在 REPL 里输入：

```text
repo-harness> /memory review
```

逐条选择 `accept`、`edit`、`reject` 或 `skip`。只有 `accept` 或 `edit` 后的内容会写入 `.repo-harness/memory/topics/*.md`。Pending queue 不进入 prompt memory、不参与 `/memory_explain`，也不会被 `safe-transfer` memory pack 导出。

### 查看记忆系统自整理

Memory Self-Iteration v1 会在 run 收尾时自动做轻量整理：过长的 episodic notes 会被压缩成 bounded summary；看起来可复用的长期事实候选只会进入 Review Queue。它不会自动写 durable topics。

如果本轮产生了候选，REPL 会在最终回答后提示你运行 `/memory review`。你也可以只读查看最近一次状态：

```text
repo-harness> /memory self_iteration
```

输出会显示最近一次 compaction、queued candidates、rejections 和 pending review 数量。这个命令不会触发 compaction，不会生成新候选，也不会修改 memory。运行报告中的 `episodic_compactions`、`self_iteration_review_queued` 和 `self_iteration_rejections` 用于复盘这一步。

### 当前 memory v1 边界

RepoHarness 这一阶段的记忆系统已经收口在三件事上：可迁移、可审核、可解释。Memory Pack 负责把 accepted durable memory 和必要现场带到其他环境；`/memory review` 负责把长期记忆写入变成人工确认动作；`/memory_explain` 负责说明某条 memory 为什么被选中。

运行报告中，`durable_review_queued` 和 `self_iteration_review_queued` 表示本轮进入 `.repo-harness/memory/review-queue.jsonl` 的候选；`durable_promotions` 只表示真正写入 durable topics 的内容；`durable_rejections` 和 `self_iteration_rejections` 表示被安全过滤拒绝的候选。这个阶段不做 Topic Configuration、Semantic Retrieval、edit distance、同义词表、embedding 或 vector DB。

### 文件摘要为什么更短也更有用

RepoHarness 读取完整 Python 文件后，会把 `file_summaries` 写成受限的结构摘要，例如 imports、classes、functions 和 constants。它仍然是短工作记忆：不保存函数体，不保存 docstring 长文本，不提高 memory 预算，也不会替代下一次必要的文件读取。

这条路径只在确认读取了完整文件时启用。除 Python AST 摘要外，Markdown 会提取 ATX headings，config 文件会提取浅层 keys / sections，Python 测试文件会优先提取 test names。片段读取、解析失败或没有可提取结构时会继续使用原来的前三行摘要。所有文件摘要仍然绑定 freshness hash；文件被修改后，旧摘要不会继续出现在下一轮 memory 文本里。

## 常见使用场景

### 分析测试失败

```bash
uv run repo-harness "run the focused tests, inspect the failure, and propose a minimal fix"
```

更稳妥的做法是在任务里说明边界：

```text
repo-harness> Please inspect tests/test_repo_harness.py and explain the likely failure before editing files.
```

### 阅读仓库结构

```text
repo-harness> Map the CLI to runtime flow. Focus on repo_harness/cli.py, repo_harness/runtime.py, and repo_harness/tools.py.
```

RepoHarness 的主链路可以概括为：

```text
repo_harness/cli.py -> RepoHarness runtime -> model output -> tool validation/execution -> session/trace/report/memory
```

### 修改小范围代码

```text
repo-harness> Fix the Windows PowerShell startup docs only. Do not change runtime behavior.
```

建议把任务写得窄一些：要改哪里、不要改哪里、验证什么。RepoHarness 更适合小步迭代，而不是一次性接收模糊的大型重构任务。

### 继续上次会话

每次运行会话会保存在 `.repo-harness/sessions/`。可以用：

```bash
uv run repo-harness --resume latest
```

也可以指定具体 session id：

```bash
uv run repo-harness --resume 20260501-224125-1f2ac5
```

### 迁移或备份 memory pack

如果你要把长期记忆带到另一台电脑，或把当前工作现场打包给自己恢复，可以在 REPL 里输入：

```text
repo-harness> /memory_pack
```

也可以使用面向脚本和高级用户的 CLI：

```bash
repo-harness memory export --preset safe-transfer --output memory-pack.zip
repo-harness memory export --preset continue-work
repo-harness memory export --preset full-recovery
repo-harness memory inspect memory-pack.zip
repo-harness memory validate memory-pack.zip
repo-harness memory import memory-pack.zip
```

三个预设的边界：

- `safe-transfer`：只导出 durable memory，默认更适合跨电脑迁移。
- `continue-work`：导出 durable memory 和 working context；导入不会覆盖当前 session，而是保存 imported working context snapshot。
- `full-recovery`：导出 durable memory、working context、sessions / checkpoints 和 run artifacts。

隐私提醒：`full-recovery` 可能包含 prompts、tool outputs、local paths、reports 和 traces。分享或导入之前，先运行 `repo-harness memory inspect` 和 `repo-harness memory validate`。

### 查看运行工件

每次运行结束后，RepoHarness 会在 `.repo-harness/runs/<run_id>/` 下写出：

- `task_state.json`：任务状态和运行摘要。
- `trace.jsonl`：模型调用、工具执行、审批和 checkpoint 等事件。
- `report.json`：面向复盘的结构化报告。

这些文件默认只保存在本地，不应该提交到仓库。

## Windows 使用注意事项

Windows 用户可以从 PowerShell 或 CMD 启动 RepoHarness。Git Bash 是可选兼容 shell，不是启动 RepoHarness 的硬依赖。

本轮 Windows 适配的边界是：让 RepoHarness 在 CMD / PowerShell 下能正常安装、启动、运行、测试，并在内部 shell 工具执行时保留 Windows 必需环境变量。它没有改变 runtime 主循环、工具审批模型、路径逃逸防护、memory、checkpoint、trace、report 或 benchmark 语义。

如果你看到 `OpenAI-compatible request failed with HTTP 401: 缺少 API Key`，说明 CLI 已经启动成功，问题是模型服务端没有收到有效 API Key。按本文的 provider 配置设置环境变量即可。

## 产品经理视角 Q&A

### Q：RepoHarness 解决的核心问题是什么？

RepoHarness 解决的是“如何让大模型在本地代码仓库里持续、可控、可复盘地工作”。它不是把聊天窗口搬进终端，而是把模型放进一个受约束的工程执行框架里：先理解当前仓库，再通过有限工具读文件、搜代码、执行命令、修改文件，并把过程记录下来。

### Q：为什么 RepoHarness 不是普通聊天机器人？

普通聊天机器人主要依赖对话上下文，回答往往脱离本地仓库事实。RepoHarness 的产品边界更接近 coding agent：它有 workspace context、tool calling、approval policy、session resume、trace/report、durable memory 和 benchmark harness。这些能力让它能够围绕真实工程任务工作，而不是只生成建议。

### Q：Agent Harness 在 RepoHarness 中体现在哪里？

Agent Harness 不是某一个模型，而是模型之外的执行编排层。RepoHarness 的 harness 由 CLI 入口、runtime 主循环、prompt prefix、工具注册与校验、审批策略、上下文管理、会话状态、checkpoint、memory 和评测框架组成。模型负责生成意图，harness 负责把意图变成受控动作，并留下可审计证据。

### Q：为什么要做工具审批、trace、memory 和 checkpoint？

这是从产品可信度出发的设计。coding agent 会读写本地文件、执行 shell 命令，如果没有审批和路径约束，风险不可接受；如果没有 trace 和 report，失败后无法复盘；如果没有 memory 和 checkpoint，长会话会反复读取同样信息，恢复能力也弱。RepoHarness 把这些能力做成默认工程机制，而不是依赖用户手工记忆。

### Q：从 0 到 1 主导 RepoHarness 能体现哪些 AI 产品经理能力？

这个项目体现的是从问题定义到可运行系统的完整闭环：识别本地代码助手的真实使用场景，拆解 Agent Harness 的关键模块，定义工具权限和安全边界，设计 session / memory / report 等可复盘机制，建立 benchmark 和测试基线，并继续推进 Windows 适配这类工程化迭代。对 AI 产品经理来说，价值在能把模型能力产品化、工程化、可验证化。

## 指标口径说明

如果你参考旧版 PDF 或历史设计文档，需要区分两个口径。

`v2.0 历史实验结果` 可以作为阶段性成果引用，例如上下文压缩、记忆命中、治理场景和 benchmark 通过率等实验结论。这些数字反映当时版本的设计收益，但不应直接冒充当前仓库的最新结果。

当前 Windows 适配版本的静态事实以当前仓库为准：

- 支持 3 类 provider：Ollama、OpenAI-compatible、Anthropic-compatible。
- 运行时暴露 7 类核心工具：`list_files`、`read_file`、`search`、`run_shell`、`write_file`、`patch_file`、`delegate`。
- 当前 benchmark 文件覆盖 12 条固定 coding tasks。
- 当前测试套件收集到 105 项测试。

本轮 Windows 适配的结论应该写成：在不改变 RepoHarness 核心 runtime、tool、memory、checkpoint、trace/report 和 benchmark 语义的前提下，补齐 Windows CMD / PowerShell 使用路径，并通过现有测试基线回归验证。

## 新维护者怎么读这个项目

不要一开始逐文件通读。先抓主链路：

```text
repo_harness/cli.py 解析命令行参数
-> 构建 RepoHarness runtime
-> 模型输出 <tool> 或 <final>
-> runtime 校验并执行工具
-> 写入 session、trace、report、memory
```

推荐阅读顺序：

1. `README.md` 和本文，先理解产品定位和启动方式。
2. `repo_harness/cli.py`，看 provider、参数和 REPL / one-shot 分流。
3. `repo_harness/runtime.py`，看 `ask()` 主循环、prompt、parse、tool execution。
4. `repo_harness/tools.py`，看工具白名单、风险等级、参数校验、路径防护。
5. `repo_harness/task_state.py`、`repo_harness/run_store.py`、`repo_harness/memory.py`、`repo_harness/context_manager.py`，看状态和持久化。
6. `tests/test_repo_harness.py` 和 `tests/test_evaluator.py`，用测试反推设计。
7. `docs/maintainer-prep/project-study-sop.md`，按维护者 SOP 做系统阅读。

学习时每完成一个主题，都跑一次相关测试：

```bash
uv run pytest tests/test_repo_harness.py -q
uv run pytest tests/test_evaluator.py -q
uv run ruff check .
```

## 第一次排障清单

- `No module named repo_harness`：确认你在项目根目录，或先执行 `pip install -e .`。
- `program not found: repo-harness`：确认依赖已安装，优先使用 `uv sync` 后再 `uv run repo-harness`。
- `HTTP 401` 或 `缺少 API Key`：CLI 启动成功，但模型 API Key 未配置或无效。
- Ollama 连接失败：确认 `ollama serve` 正在运行，模型已经 `ollama pull`。
- Windows 下 shell 命令表现不同：优先确认是否安装 Git Bash；没有 Git Bash 时 RepoHarness 会回退平台默认 shell。
- 想确认项目没被本地改坏：运行 `uv run pytest -q` 和 `uv run ruff check .`。

