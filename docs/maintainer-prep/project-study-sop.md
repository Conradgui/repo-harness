# 项目学习 SOP

## 文档说明

这份文档用于记录维护者理解项目的标准学习路径。它帮助当前维护者和未来维护者快速建立项目地图，避免一开始逐文件通读，也避免只看 README 而不了解 runtime、tools、state 和 tests 的主链路。

本文是可持续更新的 SOP。项目入口、包名、CLI 命令、本地状态目录或核心架构发生变化时，应新增日期记录或更新当前学习路径。

## 更新规则

- 学习路径发生结构性变化时新增一个日期小节。
- 如果只是微调命令或路径，可以在当前记录中更新，并在 Git commit 中说明原因。
- 旧记录中的包名、路径和命令代表当时版本事实；后续重命名时不要把历史记录伪装成当时已经存在的新名称。

## SOP 记录

### 2026-05-03：pico 项目学习路径

#### 1. 先建立运行基线

先确认本地环境、入口命令和测试套件都能工作：

```bash
uv sync
uv run pico --help
uv run pytest -q
```

完成这一轮后，应该能确认：

- CLI 命令是 `pico`，模块入口是 `python -m pico`。
- 依赖安装、帮助输出和测试基线没有环境级阻塞。
- 如果测试失败，先记录失败点，不要直接开始读源码。

#### 2. 先读主链路

`pico` 的核心链路是：

```text
pico/cli.py
  -> build_agent()
  -> Pico runtime
  -> model output: <tool> or <final>
  -> run_tool()
  -> session / trace / report / memory
```

阅读时按这个顺序走：

1. `pico/cli.py`：看参数解析、provider 选择、`build_agent()` 装配、one-shot 与 REPL 分流。
2. `pico/runtime.py`：看 `Pico.__init__`、`build_prefix`、`ask`、`parse`、`run_tool`。
3. `pico/tools.py`：看工具白名单、参数校验、risky 标记、路径边界和 shell 环境过滤。
4. `pico/task_state.py`、`pico/run_store.py`、`pico/memory.py`、`pico/context_manager.py`：看状态、持久化、记忆和上下文压缩。

读完这一层后，应该能口头说明一次用户请求如何从 CLI 输入变成模型提示、工具执行、最终答案和本地运行工件。

#### 3. 用测试反推行为

从 `tests/test_pico.py` 开始，不要先追求覆盖所有源码。优先读测试名和断言：

- agent 如何调用工具并把结果写回 history。
- malformed model output 如何触发 retry。
- session resume 和 checkpoint 如何判断 stale 或 mismatch。
- risky tool 如何通过 approval policy 控制。
- trace、report 和 task state 如何记录运行过程。
- durable memory 如何保存长期事实，以及如何拒绝敏感或临时内容。

推荐节奏：

1. 选一个主题，例如 `tool execution`。
2. 找对应测试，例如 `test_patch_file_replaces_exact_match`。
3. 先读断言并猜实现。
4. 再回到源码验证猜想。
5. 写 5 行笔记或一张小流程图。
6. 跑对应测试确认理解。

#### 4. 分主题推进

建议按下面顺序学习和复盘：

1. CLI 启动链路。
2. Runtime `ask()` 控制循环。
3. Tool registry 和 tool validation。
4. Session / resume。
5. Trace / report。
6. Memory / checkpoint。
7. Benchmark harness。

每完成一个主题，至少跑一次相关测试；如果改了代码，再跑全量测试。

#### 5. 常用验证命令

```bash
uv run python -m pico --help
uv run pytest tests/test_pico.py -q
uv run pytest -q
uv run ruff check .
```

这些命令分别覆盖 CLI 入口、核心 agent 行为、全量回归和静态检查。

#### 6. 维护者默认约定

- 第一阶段以理解和小步验证为主，不做大范围重构。
- 优先让测试描述行为，再让源码解释机制。
- 任何涉及工具执行、安全边界、持久化格式、checkpoint 或 memory 的改动，都需要补充或更新对应测试。
- `.pico/` 下的会话和运行工件是本地状态，默认不作为产品文档或源码提交对象。

#### 后续注意

如果后续执行 `RepoHarness` 全量重命名，应新增一条新的 SOP 记录，使用新的包名、CLI 命令、模块入口和状态目录。
