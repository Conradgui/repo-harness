# 项目学习 SOP

## v3 Compat Phase 2 Workflow And UX Study Note

When studying current RepoHarness, include these Phase 2 workflow modules after the Phase 1 provider/config/memory pass:

- `repo_harness/runtime_control.py` for model/tool execution seams.
- `repo_harness/skills.py` and REPL `/skills` / `/skill`.
- `repo_harness/todo_ledger.py` and todo report fields.
- `repo_harness/worker_manager.py` and worker write-scope enforcement.
- `repo_harness/sandbox.py` plus `.repo-harness.toml` sandbox config.
- `repo_harness/tui.py` and `repo_harness/release_evidence.py`.

The durable memory invariant remains:

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

## v3 Compat Phase 1 Foundation Study Note

When studying current RepoHarness, include `.repo-harness.toml`, DeepSeek provider resolution, provider reliability metadata, tool policy, `/remember`, and the v3 compat roadmap/status docs.

Durable memory still follows:

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

Phase 2 owns skills, todo ledger, worker manager, sandbox, runtime control plane layering, Textual TUI, and release evidence. Reference v3 commit: `91a7c17`; old stable reference tag: `archive-before-repoharness-rename-20260503`.

## 文档说明

这份文档用于记录维护者理解项目的标准学习路径。它帮助当前维护者和未来维护者快速建立项目地图，避免一开始逐文件通读，也避免只看 README 而不了解 runtime、tools、state 和 tests 的主链路。

本文是可持续更新的 SOP。项目入口、包名、CLI 命令、本地状态目录或核心架构发生变化时，应新增日期记录或更新当前学习路径。

## 更新规则

- 学习路径发生结构性变化时新增一个日期小节。
- 如果只是微调命令或路径，可以在当前记录中更新，并在 Git commit 中说明原因。
- 旧记录中的包名、路径和命令代表当时版本事实；后续重命名时不要把历史记录伪装成当时已经存在的新名称。

## SOP 记录

### 2026-05-03：RepoHarness 项目学习路径

#### 1. 先建立运行基线

先确认当前公开入口和测试套件都能工作：

```bash
uv sync
uv run repo-harness --help
uv run python -m repo_harness --help
uv run pytest -q
```

完成这一轮后，应该能确认：

- Python 包名是 `repo_harness`。
- CLI 命令是 `repo-harness`，模块入口是 `python -m repo_harness`。
- 本地状态目录是 `.repo-harness/`。
- 旧品牌入口和旧状态迁移兼容不再作为当前行为维护。

#### 2. 先读主链路

RepoHarness 的核心链路是：

```text
repo_harness/cli.py
  -> build_agent()
  -> RepoHarness runtime
  -> model output: <tool> or <final>
  -> run_tool()
  -> session / trace / report / memory
```

阅读时按这个顺序走：

1. `repo_harness/cli.py`：看参数解析、provider 选择、`build_agent()` 装配、one-shot 与 REPL 分流。
2. `repo_harness/runtime.py`：看 `RepoHarness.__init__`、`build_prefix`、`ask`、`parse`、`run_tool`。
3. `repo_harness/tools.py`：看工具白名单、参数校验、risky 标记、路径边界和 shell 环境过滤。
4. `repo_harness/task_state.py`、`repo_harness/run_store.py`、`repo_harness/memory.py`、`repo_harness/context_manager.py`：看状态、持久化、记忆和上下文压缩。

读完这一层后，应该能口头说明一次用户请求如何从 CLI 输入变成模型提示、工具执行、最终答案和本地运行工件。

#### 3. 用测试反推行为

从 `tests/test_repo_harness.py` 开始，不要先追求覆盖所有源码。优先读测试名和断言：

- RepoHarness 如何调用工具并把结果写回 history。
- malformed model output 如何触发 retry。
- session resume 和 checkpoint 如何判断 stale 或 mismatch。
- risky tool 如何通过 approval policy 控制。
- trace、report 和 task state 如何记录运行过程。
- durable memory 如何保存长期事实，以及如何拒绝敏感或临时内容。
- `.repo-harness/` 如何保存 session、runs、memory 和 review queue。

#### 4. 常用验证命令

```bash
uv run python -m repo_harness --help
uv run repo-harness --help
uv run pytest tests/test_repo_harness.py -q
uv run pytest -q
uv run ruff check .
```

这些命令分别覆盖模块入口、CLI 入口、核心 harness 行为、全量回归和静态检查。

#### 5. Agent 指令文件约定

`AGENTS.md` 是可选的仓库级 agent 指令文件，不是运行必需文件。当前仓库没有提交 `AGENTS.md` 或 `AGENT.md` 时，RepoHarness 会使用内置 runtime 规则、README 和 `pyproject.toml`。如果未来需要新增仓库级规则，优先使用 `AGENTS.md`。

#### 6. 文档同步门禁

维护者完成任何功能、重构或安全边界更新后，不能只停在“测试通过”。必须同步检查文档体系：

1. 用户入口是否需要更新 README。
2. 首次使用流程、REPL 命令、CLI 示例或隐私提示是否需要更新 `docs/getting-started.md`。
3. 架构边界、状态目录、运行工件或长期设计判断是否需要更新 `docs/architecture/`、`docs/review-pack/` 或 `docs/maintainer-prep/`。
4. 如果新增维护者文档，必须先更新 `docs/maintainer-prep/README.md` 的目录索引。
5. 如果变更涉及 memory、checkpoint、session、runs、安全边界或本地持久化格式，必须追加修复摘要或 roadmap，方便未来维护者复盘。

文档健全是长期可维护性的一部分。后续收尾报告应明确说明“已同步哪些文档”或“哪些文档经检查无需更新”。

### 2026-05-15：品牌残留清理后的学习基线

RepoHarness 当前学习路径只使用 `repo_harness` 包、`repo-harness` CLI、`python -m repo_harness` 模块入口和 `.repo-harness/` 状态目录。旧品牌入口、旧 prompt 和旧状态迁移兼容不再作为学习材料或维护目标。
