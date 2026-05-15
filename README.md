# RepoHarness

`repo-harness` 是一个面向代码仓库的轻量本地 coding agent。它直接跑在终端里，先看当前工作区，再用一组受约束的工具去读文件、改文件、跑命令，并把会话状态保存在本地 `.repo-harness/` 目录里。

它更像一个能在仓库里持续工作的命令行助手，不是纯聊天窗口。你可以拿它做代码排查、测试修复、仓库分析，或者让它在当前项目里执行一次性的工程任务。

如果你是第一次使用 RepoHarness，请先阅读 [RepoHarness 新手指南](docs/getting-started.md)。README 是快速入口；完整安装、API Key、Windows CMD / PowerShell、REPL 指令和产品 Q&A 都在新手指南里。

## 适合做什么

- 在本地仓库里排查测试失败
- 读取当前代码结构并给出修改建议
- 基于现有文件做小步迭代，而不是脱离仓库空想
- 在会话中保留上下文，支持继续上一次工作
- 通过 memory pack 迁移或备份可追踪的本地记忆

## 主要特性

- 包名是 `repo_harness`
- CLI 命令是 `repo-harness`
- 模块入口是 `python -m repo_harness`
- 会话保存在 `.repo-harness/sessions/`
- 每次运行的工件保存在 `.repo-harness/runs/<run_id>/`
- 长期记忆保存在 `.repo-harness/memory/`
- 支持 memory pack 的导出、导入、检查和验证
- 支持三类模型后端：
  - Ollama
  - OpenAI 兼容 Responses API
  - Anthropic 兼容 Messages API

## 安装

需要 Python 3.10+。

如果你用 `uv`，直接安装依赖：

```bash
uv sync
```

如果你已经在自己的 Python 环境里工作，也可以直接装成可编辑模式：

```bash
pip install -e .
```

## 快速开始

下面的 `uv run ...` 命令需要在 `repo-harness` 项目根目录执行，也就是当前目录下能看到 `pyproject.toml` 和 `repo_harness/` 包目录。先进入项目根目录，再运行命令。

更完整的首次配置流程见 [RepoHarness 新手指南](docs/getting-started.md)。

### macOS / Linux

在当前仓库里启动交互模式：

```bash
cd /path/to/repo-harness
uv run repo-harness
```

指定另一个工作目录：

```bash
uv run repo-harness --cwd /path/to/repo
```

直接跑一次性任务：

```bash
uv run repo-harness "inspect the test failures and propose a fix"
```

如果当前环境已经安装过包，也可以直接这样启动：

```bash
python -m repo_harness
```

### Windows PowerShell

PowerShell 使用 `$env:` 设置当前终端会话的环境变量：

```powershell
cd C:\path\to\repo-harness
$env:OPENAI_API_KEY="your-api-key"
$env:OPENAI_API_BASE="https://your-api.example/v1"
$env:OPENAI_MODEL="gpt-5.4"
uv run python -m repo_harness --help
uv run repo-harness
```

也可以指定工作目录：

```powershell
uv run repo-harness --cwd C:\path\to\repo
```

### Windows CMD

CMD 使用 `set` 设置当前终端会话的环境变量：

```bat
cd /d C:\path\to\repo-harness
set OPENAI_API_KEY=your-api-key
set OPENAI_API_BASE=https://your-api.example/v1
set OPENAI_MODEL=gpt-5.4
uv run python -m repo_harness --help
uv run repo-harness
```

也可以指定工作目录：

```bat
uv run repo-harness --cwd C:\path\to\repo
```

Windows 用户可以从 CMD 或 PowerShell 启动 `repo-harness`。如果机器上安装了 Git Bash，`repo-harness` 内部执行 shell 工具时会优先使用兼容 shell 来处理模型常见的 POSIX 风格命令；Git Bash 不是启动 `repo-harness` 的硬依赖。

## 模型后端

### Ollama

```bash
ollama serve
ollama pull qwen3.5:4b
uv run repo-harness --provider ollama --model qwen3.5:4b
```

### OpenAI 兼容接口

macOS / Linux：

```bash
export OPENAI_API_BASE="https://your-api.example/v1"
export OPENAI_API_KEY="your-api-key"
export OPENAI_MODEL="gpt-5.4"
uv run repo-harness --provider openai
```

Windows PowerShell：

```powershell
$env:OPENAI_API_BASE="https://your-api.example/v1"
$env:OPENAI_API_KEY="your-api-key"
$env:OPENAI_MODEL="gpt-5.4"
uv run repo-harness --provider openai
```

Windows CMD：

```bat
set OPENAI_API_BASE=https://your-api.example/v1
set OPENAI_API_KEY=your-api-key
set OPENAI_MODEL=gpt-5.4
uv run repo-harness --provider openai
```

### Anthropic 兼容接口

macOS / Linux：

```bash
export ANTHROPIC_API_BASE="https://your-anthropic-compatible.example/v1"
export ANTHROPIC_API_KEY="your-api-key"
export ANTHROPIC_MODEL="claude-sonnet-4-6"
uv run repo-harness --provider anthropic
```

Windows PowerShell：

```powershell
$env:ANTHROPIC_API_BASE="https://your-anthropic-compatible.example/v1"
$env:ANTHROPIC_API_KEY="your-api-key"
$env:ANTHROPIC_MODEL="claude-sonnet-4-6"
uv run repo-harness --provider anthropic
```

Windows CMD：

```bat
set ANTHROPIC_API_BASE=https://your-anthropic-compatible.example/v1
set ANTHROPIC_API_KEY=your-api-key
set ANTHROPIC_MODEL=claude-sonnet-4-6
uv run repo-harness --provider anthropic
```

如果你的服务端对多个兼容接口复用了同一套密钥，`repo-harness` 也支持按当前 provider 的 API Key 环境变量读取密钥。

## 常用交互命令

- `/help`：查看内置命令
- `/memory`：查看提炼后的工作记忆
- `/memory review`：审核 pending durable memory 候选，确认后才写入长期记忆
- `/memory self_iteration`：只读查看最近一次 Memory Self-Iteration 状态
- `/memory_explain <query>`：查看 Explainable Retrieval v1 如何为查询选择 memory
- `/memory_pack` 或 `/memory-pack`：打开 memory pack 菜单
- `/session`：查看当前会话文件路径
- `/reset`：清空当前会话状态
- `/exit` 或 `/quit`：退出 REPL

## Explainable Retrieval v1

`/memory_explain <query>` 用来调试记忆召回：它不会修改 memory，只展示 Explainable Retrieval v1 对候选记忆的选择结果。输出重点包括 `score_breakdown` 和 `selected_explanations`，说明每条 memory 因为 tag match、keyword overlap、recency、kind 或 source 等确定性信号被选中。

这项能力延续 RepoHarness 记忆系统原则：默认 lexical retrieval，轻量、可复现、文件可追踪；解释应指向本地 `.repo-harness/memory/` 中的来源，而不是依赖不可解释的外部索引。检索会对大小写、`_` / `-` 等分隔符和 camelCase / PascalCase 做确定性归一化，但不做 edit distance、同义词表或 semantic retrieval。

## Code-Aware File Summaries v1

RepoHarness 的 `file_summaries` 仍然是短工作记忆，不是代码索引或知识库。读取完整 Python 文件时，摘要会用标准库 AST 提取少量结构信号，例如 imports、classes、functions 和 constants；摘要继续受固定长度上限控制，并且仍然绑定 freshness hash。

读取完整 Markdown 文件时，摘要会提取 ATX headings，并忽略 fenced code block 内的伪标题。读取完整 JSON / TOML / INI / CFG / YAML 文件时，摘要只提取浅层 keys / sections。读取 Python 测试文件时，摘要优先提取 `test_*` functions、`Test*` classes 和 class 内 `test_*` methods。

如果读取的是片段、解析失败或没有可提取结构，系统会回退到原有的前三行短摘要。这个能力不调用模型、不引入 embedding / database / background service，也不改变 memory section 预算。

## Durable Memory Review Queue

RepoHarness 不会再把模型最终回答里解析出的长期事实直接写入 durable topics。用户明确要求保存长期记忆时，候选会先进入：

```text
.repo-harness/memory/review-queue.jsonl
```

在 REPL 里输入 `/memory review` 可以逐条审核：

- `accept`：把候选写入固定四类 durable topics。
- `edit`：先编辑 topic 或 text，再写入 durable topics。
- `reject`：拒绝候选，不写入 durable memory。
- `skip`：保留 pending，稍后再处理。

secret-shaped、临时任务状态和噪声输出不会进入 queue；人工 edit 后也会再次执行同一类安全过滤。Pending queue 不进入 prompt memory、不参与 `/memory_explain`，也不会被 `safe-transfer` memory pack 导出。

## Memory Self-Iteration v1

Memory Self-Iteration v1 是透明、可控的轻量自整理。每轮 run 收尾时，RepoHarness 可以把过长的 episodic notes 压缩成 bounded summary，并把看起来可复用的长期事实候选送入 Review Queue；它不会直接写 `.repo-harness/memory/topics/*.md`。

如果本轮产生了候选，REPL 会在最终回答后提示你运行 `/memory review`。你也可以输入：

```text
/memory self_iteration
```

这个入口只读展示最近一次 self-iteration 的 compaction、queued candidates、rejections 和 pending review 数量；它不会触发 compaction，不会生成新候选，也不会写 durable memory。

`report.json` 会记录 `episodic_compactions`、`self_iteration_review_queued` 和 `self_iteration_rejections`。这些字段用于解释系统做了什么；长期记忆最终控制点仍然只有 `/memory review`。

## Memory v1 当前边界

当前记忆系统 v1 的稳定目标是“可迁移、可审核、可解释”，不是扩大语义检索复杂度：

- 可迁移：Memory Pack 支持 `safe-transfer`、`continue-work` 和 `full-recovery` 三种 preset。
- 可审核：所有 durable memory 候选先进入 `review-queue.jsonl`；只有 `/memory review` 的 accept/edit 会写入 durable topics。
- 可解释：`/memory_explain` 和 `selected_explanations` 解释被选中 memory 的确定性 lexical / fuzzy lexical 信号。

相关运行报告字段也保持固定语义：`durable_review_queued` 和 `self_iteration_review_queued` 表示本轮入队候选，`durable_promotions` 只表示真正写入 durable topics 的内容，`durable_rejections` 和 `self_iteration_rejections` 表示被安全过滤拒绝的候选。

## Memory Pack

Memory pack 用来迁移、备份或检查 RepoHarness 的本地记忆系统。它保持当前记忆系统的设计原则：确定性、轻量、文件可追踪、分层清晰。

普通用户可以在 REPL 里输入：

```text
repo-harness> /memory_pack
```

`/memory-pack` 是同一个入口的别名。菜单按最终效果组织：

- `safe-transfer`：只导出 durable knowledge，适合把长期项目记忆迁移到另一台电脑。
- `continue-work`：导出 durable knowledge 和 working context；导入时 working context 会保存为独立 snapshot，不覆盖当前 session。
- `full-recovery`：导出 durable knowledge、working context、sessions / checkpoints 和 run artifacts。

高级用户可以直接使用 CLI：

```bash
repo-harness memory export --preset safe-transfer
repo-harness memory export --preset continue-work
repo-harness memory export --preset full-recovery
repo-harness memory inspect memory-pack.zip
repo-harness memory validate memory-pack.zip
repo-harness memory import memory-pack.zip
```

导入默认使用 conservative merge：只复制缺失内容，不覆盖已有 memory、session 或 run 文件。`full-recovery` 可能包含 prompts、tool outputs、local paths、reports 和 traces；分享或导入之前，先用 `repo-harness memory inspect` 和 `repo-harness memory validate` 检查。

## 安全与持久化

`repo-harness` 不会默认把所有动作都放开。像 shell 执行、文件写入这类高风险操作，会受审批模式控制：

- `--approval ask`
- `--approval auto`
- `--approval never`

每次运行结束后，都会在 `.repo-harness/runs/<run_id>/` 下写出这些文件：

- `task_state.json`
- `trace.jsonl`
- `report.json`

这些内容默认只保存在本地。

## Agent 指令文件

RepoHarness 会在构建工作区快照时读取可选的 `AGENTS.md`（复数）作为仓库级 agent 指令。这个文件不是运行必需文件；当前仓库没有提交 `AGENTS.md` 或 `AGENT.md` 时，RepoHarness 会继续使用内置 runtime 规则、README 和 `pyproject.toml`。

## 开发

如果装了 Ruff，可以这样检查：

```bash
uv run ruff check .
```

新维护者可以从 [维护者项目学习 SOP](docs/maintainer-prep/project-study-sop.md) 开始，按 CLI、runtime、tools、state、tests 的顺序建立项目地图。
