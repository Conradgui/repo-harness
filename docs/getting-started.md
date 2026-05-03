# Pico 新手指南

`pico` 是一个运行在本地终端里的轻量 coding agent，也可以理解为一个面向代码仓库的 Agent Harness：它把模型、仓库上下文、受约束工具、审批机制、会话状态、运行工件和记忆系统组织成一个可持续工作的命令行助手。

这份指南面向三类读者：

- 第一次使用 Pico 的用户：快速配置模型后端，把 CLI 跑起来。
- 新维护者：知道应该从哪条主链路理解项目。
- HR / 面试官：快速理解这个项目体现出的 AI 产品设计、Agent 架构和工程落地能力。

README 是快速入口；如果你想从“完全没用过”到“能配置、能使用、能解释 Pico”，建议按本文顺序阅读。

## 5 分钟快速跑起来

先确认当前终端已经进入 Pico 项目根目录。这个目录下应该能看到 `pyproject.toml` 和 `pico/` 包目录。

macOS / Linux：

```bash
cd /path/to/pico
uv sync
uv run python -m pico --help
uv run pico
```

Windows PowerShell：

```powershell
cd C:\Users\Administrator\Desktop\cc\P1test
uv sync
uv run python -m pico --help
uv run pico
```

Windows CMD：

```bat
cd /d C:\Users\Administrator\Desktop\cc\P1test
uv sync
uv run python -m pico --help
uv run pico
```

如果你在 `C:\Users\Administrator` 这类非项目目录直接运行 `uv run python -m pico --help`，Python 找不到当前仓库里的 `pico` 包，可能会看到 `No module named pico` 或 `program not found`。解决方式不是改代码，而是先进入项目根目录，或者先执行 `pip install -e .` 把包安装到当前 Python 环境。

## 三类模型后端怎么配置

Pico 支持三类模型后端：Ollama、OpenAI 兼容 Responses API、Anthropic 兼容 Messages API。CLI 默认使用 `openai` provider。

### Ollama：本地模型，不需要 API Key

Ollama 适合本地试跑和离线实验。它不需要 API Key，但需要本机已经安装并启动 Ollama。

```bash
ollama serve
ollama pull qwen3.5:4b
uv run pico --provider ollama --model qwen3.5:4b
```

PowerShell 和 CMD 里命令相同。注意：`ollama serve` 通常需要保持运行；可以单独开一个终端窗口运行服务，再在另一个终端启动 Pico。

### OpenAI 兼容接口：默认推荐路径

Pico 默认 provider 是 `openai`，默认模型是 `gpt-5.4`。如果不显式传 `--base-url`，项目会使用默认 OpenAI-compatible 服务地址。你至少需要配置 `OPENAI_API_KEY`。

macOS / Linux：

```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_API_BASE="https://your-api.example/v1"
export OPENAI_MODEL="gpt-5.4"
uv run pico --provider openai
```

Windows PowerShell：

```powershell
$env:OPENAI_API_KEY="your-api-key"
$env:OPENAI_API_BASE="https://your-api.example/v1"
$env:OPENAI_MODEL="gpt-5.4"
uv run pico --provider openai
```

Windows CMD：

```bat
set OPENAI_API_KEY=your-api-key
set OPENAI_API_BASE=https://your-api.example/v1
set OPENAI_MODEL=gpt-5.4
uv run pico --provider openai
```

如果你只想验证 CLI 是否能启动，可以先运行 `uv run python -m pico --help`。这个命令不需要 API Key。进入 `pico>` 后发送真实任务时，模型请求才会需要有效密钥。

### Anthropic 兼容接口

Anthropic-compatible provider 默认模型是 `claude-sonnet-4-6`。密钥读取顺序是 `ANTHROPIC_API_KEY`、`RIGHT_CODES_API_KEY`、`OPENAI_API_KEY`，这样可以兼容复用同一套服务端密钥的部署方式。

macOS / Linux：

```bash
export ANTHROPIC_API_KEY="your-api-key"
export ANTHROPIC_API_BASE="https://www.right.codes/claude/v1"
export ANTHROPIC_MODEL="claude-sonnet-4-6"
uv run pico --provider anthropic
```

Windows PowerShell：

```powershell
$env:ANTHROPIC_API_KEY="your-api-key"
$env:ANTHROPIC_API_BASE="https://www.right.codes/claude/v1"
$env:ANTHROPIC_MODEL="claude-sonnet-4-6"
uv run pico --provider anthropic
```

Windows CMD：

```bat
set ANTHROPIC_API_KEY=your-api-key
set ANTHROPIC_API_BASE=https://www.right.codes/claude/v1
set ANTHROPIC_MODEL=claude-sonnet-4-6
uv run pico --provider anthropic
```

## Pico 里可以输入什么

启动后你会看到 `pico>`。这不是系统 shell，而是 Pico 的交互式 REPL。你可以直接输入自然语言任务，也可以输入内置命令。

常用任务示例：

```text
pico> inspect the test failures and propose a fix
pico> read README and summarize how this project starts
pico> find where run_shell validates arguments
pico> update the docs for Windows PowerShell usage
```

常用内置命令：

- `/help`：查看 REPL 内置命令。
- `/memory`：查看当前会话提炼出来的工作记忆。
- `/session`：查看当前 session 文件路径。
- `/reset`：清空当前会话状态。
- `/exit` 或 `/quit`：退出 Pico。

注意：在 `pico>` 里输入 `cd C:\path\to\repo` 或 `uv run pico`，Pico 会把它当成给 agent 的自然语言任务，不会像普通终端那样直接执行。要切换目录或重新启动 Pico，请先 `/exit` 回到 PowerShell / CMD / shell。

## 常见使用场景

### 分析测试失败

```bash
uv run pico "run the focused tests, inspect the failure, and propose a minimal fix"
```

更稳妥的做法是在任务里说明边界：

```text
pico> Please inspect tests/test_pico.py and explain the likely failure before editing files.
```

### 阅读仓库结构

```text
pico> Map the CLI to runtime flow. Focus on pico/cli.py, pico/runtime.py, and pico/tools.py.
```

Pico 的主链路可以概括为：

```text
pico/cli.py -> Pico runtime -> model output -> tool validation/execution -> session/trace/report/memory
```

### 修改小范围代码

```text
pico> Fix the Windows PowerShell startup docs only. Do not change runtime behavior.
```

建议把任务写得窄一些：要改哪里、不要改哪里、验证什么。Pico 更适合小步迭代，而不是一次性接收模糊的大型重构任务。

### 继续上次会话

每次运行会话会保存在 `.pico/sessions/`。可以用：

```bash
uv run pico --resume latest
```

也可以指定具体 session id：

```bash
uv run pico --resume 20260501-224125-1f2ac5
```

### 查看运行工件

每次运行结束后，Pico 会在 `.pico/runs/<run_id>/` 下写出：

- `task_state.json`：任务状态和运行摘要。
- `trace.jsonl`：模型调用、工具执行、审批和 checkpoint 等事件。
- `report.json`：面向复盘的结构化报告。

这些文件默认只保存在本地，不应该提交到仓库。

## Windows 使用注意事项

Windows 用户可以从 PowerShell 或 CMD 启动 Pico。Git Bash 是可选兼容 shell，不是启动 Pico 的硬依赖。

本轮 Windows 适配的边界是：让 Pico 在 CMD / PowerShell 下能正常安装、启动、运行、测试，并在内部 shell 工具执行时保留 Windows 必需环境变量。它没有改变 runtime 主循环、工具审批模型、路径逃逸防护、memory、checkpoint、trace、report 或 benchmark 语义。

如果你看到 `OpenAI-compatible request failed with HTTP 401: 缺少 API Key`，说明 CLI 已经启动成功，问题是模型服务端没有收到有效 API Key。按本文的 provider 配置设置环境变量即可。

## 产品经理视角 Q&A

### Q：Pico 解决的核心问题是什么？

Pico 解决的是“如何让大模型在本地代码仓库里持续、可控、可复盘地工作”。它不是把聊天窗口搬进终端，而是把模型放进一个受约束的工程执行框架里：先理解当前仓库，再通过有限工具读文件、搜代码、执行命令、修改文件，并把过程记录下来。

### Q：为什么 Pico 不是普通聊天机器人？

普通聊天机器人主要依赖对话上下文，回答往往脱离本地仓库事实。Pico 的产品边界更接近 coding agent：它有 workspace context、tool calling、approval policy、session resume、trace/report、durable memory 和 benchmark harness。这些能力让它能够围绕真实工程任务工作，而不是只生成建议。

### Q：Agent Harness 在 Pico 中体现在哪里？

Agent Harness 不是某一个模型，而是模型之外的执行编排层。Pico 的 harness 由 CLI 入口、runtime 主循环、prompt prefix、工具注册与校验、审批策略、上下文管理、会话状态、checkpoint、memory 和评测框架组成。模型负责生成意图，harness 负责把意图变成受控动作，并留下可审计证据。

### Q：为什么要做工具审批、trace、memory 和 checkpoint？

这是从产品可信度出发的设计。coding agent 会读写本地文件、执行 shell 命令，如果没有审批和路径约束，风险不可接受；如果没有 trace 和 report，失败后无法复盘；如果没有 memory 和 checkpoint，长会话会反复读取同样信息，恢复能力也弱。Pico 把这些能力做成默认工程机制，而不是依赖用户手工记忆。

### Q：从 0 到 1 主导 Pico 能体现哪些 AI 产品经理能力？

这个项目体现的是从问题定义到可运行系统的完整闭环：识别本地代码助手的真实使用场景，拆解 Agent Harness 的关键模块，定义工具权限和安全边界，设计 session / memory / report 等可复盘机制，建立 benchmark 和测试基线，并继续推进 Windows 适配这类工程化迭代。对 AI 产品经理来说，价值不只在“会用模型”，而在能把模型能力产品化、工程化、可验证化。

## 指标口径说明

如果你参考旧版 PDF 或历史设计文档，需要区分两个口径。

`v2.0 历史实验结果` 可以作为阶段性成果引用，例如上下文压缩、记忆命中、治理场景和 benchmark 通过率等实验结论。这些数字反映当时版本的设计收益，但不应直接冒充当前仓库的最新结果。

当前 Windows 适配版本的静态事实以当前仓库为准：

- 支持 3 类 provider：Ollama、OpenAI-compatible、Anthropic-compatible。
- 运行时暴露 7 类核心工具：`list_files`、`read_file`、`search`、`run_shell`、`write_file`、`patch_file`、`delegate`。
- 当前 benchmark 文件覆盖 12 条固定 coding tasks。
- 当前测试套件收集到 105 项测试。

本轮 Windows 适配的结论应该写成：在不改变 Pico 核心 runtime、tool、memory、checkpoint、trace/report 和 benchmark 语义的前提下，补齐 Windows CMD / PowerShell 使用路径，并通过现有测试基线回归验证。

## 新维护者怎么读这个项目

不要一开始逐文件通读。先抓主链路：

```text
pico/cli.py 解析命令行参数
-> 构建 Pico runtime
-> 模型输出 <tool> 或 <final>
-> runtime 校验并执行工具
-> 写入 session、trace、report、memory
```

推荐阅读顺序：

1. `README.md` 和本文，先理解产品定位和启动方式。
2. `pico/cli.py`，看 provider、参数和 REPL / one-shot 分流。
3. `pico/runtime.py`，看 `ask()` 主循环、prompt、parse、tool execution。
4. `pico/tools.py`，看工具白名单、风险等级、参数校验、路径防护。
5. `pico/task_state.py`、`pico/run_store.py`、`pico/memory.py`、`pico/context_manager.py`，看状态和持久化。
6. `tests/test_pico.py` 和 `tests/test_evaluator.py`，用测试反推设计。
7. `docs/maintainer-prep/project-study-sop.md`，按维护者 SOP 做系统阅读。

学习时每完成一个主题，都跑一次相关测试：

```bash
uv run pytest tests/test_pico.py -q
uv run pytest tests/test_evaluator.py -q
uv run ruff check .
```

## 第一次排障清单

- `No module named pico`：确认你在项目根目录，或先执行 `pip install -e .`。
- `program not found: pico`：确认依赖已安装，优先使用 `uv sync` 后再 `uv run pico`。
- `HTTP 401` 或 `缺少 API Key`：CLI 启动成功，但模型 API Key 未配置或无效。
- Ollama 连接失败：确认 `ollama serve` 正在运行，模型已经 `ollama pull`。
- Windows 下 shell 命令表现不同：优先确认是否安装 Git Bash；没有 Git Bash 时 Pico 会回退平台默认 shell。
- 想确认项目没被本地改坏：运行 `uv run pytest -q` 和 `uv run ruff check .`。
