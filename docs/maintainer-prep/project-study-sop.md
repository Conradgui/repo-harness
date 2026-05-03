# 吃透 pico 项目的 SOP

这份 SOP 面向第一次接手 `pico` 的维护者。目标不是逐文件通读，而是先抓住主链路，再用测试反推行为，最后形成可维护、可修改的项目理解。

版本管理口径：本 SOP 需要跟随项目入口、包名、CLI 命令和本地状态目录更新。后续如果执行 `RepoHarness` 全量重命名，应同步替换本文中的命令和路径，而不是继续保留旧入口作为当前用法。

## 1. 先建立运行基线

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

## 2. 先读主链路

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

## 3. 用测试反推行为

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

## 4. 分主题推进

建议按下面顺序学习和复盘：

1. CLI 启动链路。
2. Runtime `ask()` 控制循环。
3. Tool registry 和 tool validation。
4. Session / resume。
5. Trace / report。
6. Memory / checkpoint。
7. Benchmark harness。

每完成一个主题，至少跑一次相关测试；如果改了代码，再跑全量测试。

## 5. 常用验证命令

```bash
uv run python -m pico --help
uv run pytest tests/test_pico.py -q
uv run pytest -q
uv run ruff check .
```

这些命令分别覆盖 CLI 入口、核心 agent 行为、全量回归和静态检查。

## 6. 维护者默认约定

- 第一阶段以理解和小步验证为主，不做大范围重构。
- 优先让测试描述行为，再让源码解释机制。
- 任何涉及工具执行、安全边界、持久化格式、checkpoint 或 memory 的改动，都需要补充或更新对应测试。
- `.pico/` 下的会话和运行工件是本地状态，默认不作为产品文档或源码提交对象。
