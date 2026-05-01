# pico

`pico` 是一个面向代码仓库的轻量本地 coding agent。它直接跑在终端里，先看当前工作区，再用一组受约束的工具去读文件、改文件、跑命令，并把会话状态保存在本地 `.pico/` 目录里。

它更像一个能在仓库里持续工作的命令行助手，不是纯聊天窗口。你可以拿它做代码排查、测试修复、仓库分析，或者让它在当前项目里执行一次性的工程任务。

## 适合做什么

- 在本地仓库里排查测试失败
- 读取当前代码结构并给出修改建议
- 基于现有文件做小步迭代，而不是脱离仓库空想
- 在会话中保留上下文，支持继续上一次工作

## 主要特性

- 包名是 `pico`
- CLI 命令是 `pico`
- 模块入口是 `python -m pico`
- 会话保存在 `.pico/sessions/`
- 每次运行的工件保存在 `.pico/runs/<run_id>/`
- 支持三类模型后端：
  - Ollama
  - OpenAI 兼容 Responses API
  - Anthropic 兼容 Messages API

## 使用截图

CLI 帮助信息：

![pico help](assets/screenshots/pico-help.png)

启动界面：

![pico start](assets/screenshots/pico-start.png)

REPL 内置命令与会话路径：

![pico repl](assets/screenshots/pico-repl.png)

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

### macOS / Linux

在当前仓库里启动交互模式：

```bash
uv run pico
```

指定另一个工作目录：

```bash
uv run pico --cwd /path/to/repo
```

直接跑一次性任务：

```bash
uv run pico "inspect the test failures and propose a fix"
```

如果当前环境已经安装过包，也可以直接这样启动：

```bash
python -m pico
```

### Windows PowerShell

PowerShell 使用 `$env:` 设置当前终端会话的环境变量：

```powershell
$env:OPENAI_API_KEY="your-api-key"
$env:OPENAI_API_BASE="https://your-api.example/v1"
$env:OPENAI_MODEL="gpt-5.4"
uv run python -m pico --help
uv run pico
```

也可以指定工作目录：

```powershell
uv run pico --cwd C:\path\to\repo
```

### Windows CMD

CMD 使用 `set` 设置当前终端会话的环境变量：

```bat
set OPENAI_API_KEY=your-api-key
set OPENAI_API_BASE=https://your-api.example/v1
set OPENAI_MODEL=gpt-5.4
uv run python -m pico --help
uv run pico
```

也可以指定工作目录：

```bat
uv run pico --cwd C:\path\to\repo
```

Windows 用户可以从 CMD 或 PowerShell 启动 `pico`。如果机器上安装了 Git Bash，`pico` 内部执行 shell 工具时会优先使用兼容 shell 来处理模型常见的 POSIX 风格命令；Git Bash 不是启动 `pico` 的硬依赖。

## 模型后端

### Ollama

```bash
ollama serve
ollama pull qwen3.5:4b
uv run pico --provider ollama --model qwen3.5:4b
```

### OpenAI 兼容接口

macOS / Linux：

```bash
export OPENAI_API_BASE="https://your-api.example/v1"
export OPENAI_API_KEY="your-api-key"
export OPENAI_MODEL="gpt-5.4"
uv run pico --provider openai
```

Windows PowerShell：

```powershell
$env:OPENAI_API_BASE="https://your-api.example/v1"
$env:OPENAI_API_KEY="your-api-key"
$env:OPENAI_MODEL="gpt-5.4"
uv run pico --provider openai
```

Windows CMD：

```bat
set OPENAI_API_BASE=https://your-api.example/v1
set OPENAI_API_KEY=your-api-key
set OPENAI_MODEL=gpt-5.4
uv run pico --provider openai
```

### Anthropic 兼容接口

macOS / Linux：

```bash
export ANTHROPIC_API_BASE="https://www.right.codes/claude/v1"
export ANTHROPIC_API_KEY="your-api-key"
export ANTHROPIC_MODEL="claude-sonnet-4-6"
uv run pico --provider anthropic
```

Windows PowerShell：

```powershell
$env:ANTHROPIC_API_BASE="https://www.right.codes/claude/v1"
$env:ANTHROPIC_API_KEY="your-api-key"
$env:ANTHROPIC_MODEL="claude-sonnet-4-6"
uv run pico --provider anthropic
```

Windows CMD：

```bat
set ANTHROPIC_API_BASE=https://www.right.codes/claude/v1
set ANTHROPIC_API_KEY=your-api-key
set ANTHROPIC_MODEL=claude-sonnet-4-6
uv run pico --provider anthropic
```

如果你的服务端对多个兼容接口复用了同一套密钥，`pico` 也支持从 `ANTHROPIC_API_KEY` 回退到 `RIGHT_CODES_API_KEY` 或 `OPENAI_API_KEY`。

## 常用交互命令

- `/help`：查看内置命令
- `/memory`：查看提炼后的工作记忆
- `/session`：查看当前会话文件路径
- `/reset`：清空当前会话状态
- `/exit` 或 `/quit`：退出 REPL

## 安全与持久化

`pico` 不会默认把所有动作都放开。像 shell 执行、文件写入这类高风险操作，会受审批模式控制：

- `--approval ask`
- `--approval auto`
- `--approval never`

每次运行结束后，都会在 `.pico/runs/<run_id>/` 下写出这些文件：

- `task_state.json`
- `trace.jsonl`
- `report.json`

这些内容默认只保存在本地，不需要跟仓库一起提交。

## 开发

如果装了 Ruff，可以这样检查：

```bash
uv run ruff check .
```

新维护者可以从 [吃透 pico 项目的 SOP](docs/maintainer-prep/project-study-sop.md) 开始，按 CLI、runtime、tools、state、tests 的顺序建立项目地图。
