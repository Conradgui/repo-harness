# P2-2：trace span 树接入（方案 A）

> 背景：双 Agent 架构分析确认 `repo_harness/core/runtime_events.py` 的 `build_runtime_event` 是**未接入的死代码半成品**——它有完整的 span 树逻辑（`parent_span_id` + 顺序 `span_id`），但零调用方、零测试，且引用的 `runtime._last_trace_span_id`/`_trace_seq` 在 runtime.py **从未定义**（一旦调用必 AttributeError）。
> 实际运行的 `runtime.py:emit_trace` 用随机 uuid span、无 parent，导致多 worker/子 agent 场景无法追溯调用链。
> 方案 A（用户已确认）：把 span 树真正接入 `emit_trace`，并清理死代码。

## 现状（已核实）

- `runtime.py:685-699 emit_trace`：`span_id = "span_" + uuid.uuid4().hex[:8]`，无 `parent_span_id`。
- `runtime.py:__init__`：无 `_trace_seq`、`_last_trace_span_id` 初始化。
- `core/runtime_events.py`：`build_runtime_event` 唯一定义处，无调用、无测试。
- `core/runtime_secrets.py`：`redact(runtime, value)` 死代码，无调用方。
- 测试 `tests/test_runtime_evidence_acceptance.py:44-48`：断言 `tool_event["span_id"]` 存在、`phase=="tool"`、`turn_id`、`artifact_paths`——**不依赖 span 格式**，顺序号兼容。

## 改动（行为级，需审核）

### 1. `runtime.py` `__init__` 初始化 span 状态

在 `__init__` 末尾（`self._finalize_runtime_evidence` 等初始化附近）增加：

```python
self._trace_seq = 0
self._last_trace_span_id = {}
```

### 2. `runtime.py` `emit_trace` 接入 span 树

修改 `emit_trace`（685-699），在现有 `payload.setdefault("span_id", ...)` 处改为：

```python
parent = self._last_trace_span_id.get(getattr(task_state, "run_id", ""), "")
payload.setdefault("parent_span_id", parent)
self._trace_seq += 1
payload.setdefault("span_id", f"span_{self._trace_seq:06d}")
self._last_trace_span_id[getattr(task_state, "run_id", "")] = payload["span_id"]
```

**保持所有其它字段不变**（phase/status/run_id/turn_id/artifact_paths/duration_ms/error_type/event/created_at），保持 `redact_artifact` 前置脱敏。

### 3. 移除死代码

- 删除 `repo_harness/core/runtime_events.py`（未接入的半成品，被 emit_trace 直接实现替代）。
- 删除 `repo_harness/core/runtime_secrets.py`（`redact()` 无调用方，`runtime.redact_artifact` 已有等价转发）。

**红线**：ADR-002 说"安全边界用开关而非删除实现"——但这两个文件是死代码（非能力、非安全边界），删除符合"清理无人引用死代码"的既有先例（v5 删除过同批 `session_events.py`/`engine.py` shim）。删除前必须确认无任何 import（已核实：全仓库仅定义处）。

### 4. 新增行为测试

新增 `tests/test_trace_span_tree.py`（或并入现有 trace 测试），用 `build_agent` 驱动一轮含工具调用 + final 的对话，断言：

- 同一 run 的 trace 事件中 `span_id` 单调递增（顺序号格式 `span_000001` 等）。
- 首个事件 `parent_span_id` 为空；后续事件 `parent_span_id == 前一个事件 span_id`（同一 run 内线性链）。
- `tool_executed` 事件保留 `phase=="tool"`、`span_id` 存在、`turn_id` 正确。
- **不锁死** span 格式字符串（行为测试，ADR-003：只测行为不测形状）——断言存在/递增/链接，不断言精确格式。

## 门禁

```bash
uv run ruff check .
uv run pytest tests/ -q --tb=short   # 全量，含新测试
uv run pytest tests/test_docs_integrity.py tests/test_documented_snippets.py -q
```

## 红线

- 不改其它 trace 字段、不改 report/task_state 结构、不改 event 语义。
- 测试只测行为（span 存在/递增/链接），不断言 span 字符串格式。
- 删除死代码前已核实零 import、零测试引用。
- 不新增依赖、不改 model client / provider 逻辑。
