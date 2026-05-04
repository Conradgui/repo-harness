# RepoHarness

`repo-harness` 是一个面向代码仓库的轻量本地 coding agent。它直接跑在终端里，先看当前工作区，再用一组受约束的工具去读文件、改文件、跑命令，并把会话状态保存在本地 `.repo-harness/` 目录里。

它更像一个能在仓库里持续工作的命令行助手，不是纯聊天窗口。你可以拿它做代码排查、测试修复、仓库分析，或者让它在当前项目里执行一次性的工程任务。

如果你是第一次使用 RepoHarness，请先阅读 [RepoHarness 新手指南](docs/getting-started.md)。README 是快速入口；完整安装、API Key、Windows CMD / PowerShell、REPL 指令和产品 Q&A 都在新手指南里。

## 适合做什么

- 在本地仓库里排查测试失败
- 读取当前代码结构并给出修改建议
- 基于现有文件做小步迭代，而不是脱离仓库空想
- 在会话中保留上下文，支持继续上一次工作

## 主要特性

- 包名是 `repo_harness`
- CLI 命令是 `repo-harness`
- 模块入口是 `python -m repo_harness`
- 会话保存在 `.repo-harness/sessions/`
- 每次运行的工件保存在 `.repo-harness/runs/<run_id>/`
- 支持三类模型后端：
  - Ollama
  - OpenAI 兼容 Responses API
  - Anthropic 兼容 Messages API

## 使用截图

CLI 帮助信息：

![repo-harness help](assets/screenshots/repo-harness-help.png)

启动界面：

![repo-harness start](assets/screenshots/repo-harness-start.png)

REPL 内置命令与会话路径：

![repo-harness repl](assets/screenshots/repo-harness-repl.png)

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

下面的 `uv run ...` 命令需要在 `repo-harness` 项目根目录执行，也就是当前目录下能看到 `pyproject.toml` 和 `repo_harness/` 包目录。比如这个仓库在 Windows 上位于 `C:\Users\Administrator\Desktop\cc\P1test` 时，先进入该目录，再运行命令。

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
cd C:\Users\Administrator\Desktop\cc\P1test
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
cd /d C:\Users\Administrator\Desktop\cc\P1test
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
export ANTHROPIC_API_BASE="https://www.right.codes/claude/v1"
export ANTHROPIC_API_KEY="your-api-key"
export ANTHROPIC_MODEL="claude-sonnet-4-6"
uv run repo-harness --provider anthropic
```

Windows PowerShell：

```powershell
$env:ANTHROPIC_API_BASE="https://www.right.codes/claude/v1"
$env:ANTHROPIC_API_KEY="your-api-key"
$env:ANTHROPIC_MODEL="claude-sonnet-4-6"
uv run repo-harness --provider anthropic
```

Windows CMD：

```bat
set ANTHROPIC_API_BASE=https://www.right.codes/claude/v1
set ANTHROPIC_API_KEY=your-api-key
set ANTHROPIC_MODEL=claude-sonnet-4-6
uv run repo-harness --provider anthropic
```

如果你的服务端对多个兼容接口复用了同一套密钥，`repo-harness` 也支持从 `ANTHROPIC_API_KEY` 回退到 `RIGHT_CODES_API_KEY` 或 `OPENAI_API_KEY`。

## 常用交互命令

- `/help`：查看内置命令
- `/memory`：查看提炼后的工作记忆
- `/session`：查看当前会话文件路径
- `/reset`：清空当前会话状态
- `/exit` 或 `/quit`：退出 REPL

## 安全与持久化

`repo-harness` 不会默认把所有动作都放开。像 shell 执行、文件写入这类高风险操作，会受审批模式控制：

- `--approval ask`
- `--approval auto`
- `--approval never`

每次运行结束后，都会在 `.repo-harness/runs/<run_id>/` 下写出这些文件：

- `task_state.json`
- `trace.jsonl`
- `report.json`

这些内容默认只保存在本地，不需要跟仓库一起提交。

## Agent 指令文件

RepoHarness 会在构建工作区快照时读取可选的 `AGENTS.md`（复数）作为仓库级 agent 指令。这个文件不是运行必需文件；当前仓库没有提交 `AGENTS.md` 或 `AGENT.md` 时，RepoHarness 会继续使用内置 runtime 规则、README 和 `pyproject.toml`。

## 开发

如果装了 Ruff，可以这样检查：

```bash
uv run ruff check .
```

新维护者可以从 [维护者项目学习 SOP](docs/maintainer-prep/project-study-sop.md) 开始，按 CLI、runtime、tools、state、tests 的顺序建立项目地图。

