# 子母 Agent 记忆与审计链路设计提案（最小可行版）

> 目标（用户提出）：
> 1. 审计链路简洁高效。
> 2. 子 Agent 运行时上下文干净，只收到 parent 的控制。
> 3. parent 可随时监控 child 状态与动向。
> 4. 记忆单向透明：parent 可见 child；child 只能看到 parent 给的部分。
>
> 参考：Claude Code（子代理上下文隔离、结果摘要返回、Agent Memory 作用域）、Codex（AGENTS.md 层级、两阶段管道、只存不可推导信息）、OpenTelemetry Trace Context（parent_span_id 关联）、多 Agent 原则（"让 Agent 出主意，让 Harness 拿决定"）。
>
> **本版为双 Agent 审核后的最小可行修订**：原提案发现两处实质偏差（阶段 3 诊断错误 + 遗漏并发竞态；ChildContext 混"控制"与"信息注入"），已按最小可行收敛。

---

## 一、现状事实（双 Agent + 本地分析确认，带证据）

1. **child durable 已自动写共享队列**：`engine.py:388` 每个 run 结束（含 child）都调 `promote_durable_memory` → `enqueue_durable_reviews` → `DurableMemoryReviewQueue._write`。child 与 parent 共享 `workspace_root` → 同 `durable_root = workspace_root/.repo-harness/memory` → **同一 `review-queue.jsonl`**（memory.py:704/1154）。
2. **`_write` 无锁**（memory.py:395-400）：`load() → 内存改 → tmp+replace` 全量写回，无 threading.Lock/flock。后台 worker（`threading.Thread`）与 parent 主线程并发写 → **丢更新竞态（真实缺陷）**。
3. **delegate 泄漏 parent history**：`tools/__init__.py:467` `child.session["memory"]["notes"] = [clip(agent.history_text(), 300)]`——parent 历史泄漏给 child，违反"child 只收 parent 给的部分"。
4. **child 记忆天然隔离**：child 是独立 session + 独立 LayeredMemory（`build_child_runtime` 不传 session）；child 的 episodic notes 不合并进 parent（现状成立）。
5. **parent 可见 child 候选**：`pending_durable_reviews()` 每次从磁盘 load，parent 只要重新查询就能看到 child 写进去的候选。
6. **后台 worker 无运行中可见性**：`spawn` 只返回 `_public_payload(status="started")`（id/description）；child run_dir/trace 只在 `_finish_task` 时经 `collect_worker_artifacts` 收集。
7. **trace 父子零关联**：`emit_trace` 用随机 uuid span（runtime.py:693），无 `parent_span_id`；`core/runtime_events.py`、`core/runtime_secrets.py` 是死代码（零 import、引用不存在属性）。

---

## 二、最小可行方案（4 项）

### M1. 上下文干净（解决"child 只收 parent 给的部分"）
- **改**：`tool_delegate` 删掉 `child.session["memory"]["notes"] = [clip(agent.history_text(), 300)]`（tools/__init__.py:467）。
- **保**：`child.session["memory"]["task"] = task`（task 是 parent 显式给 child 的任务指示——这就是"parent 给的部分"）。
- **效果**：child 上下文 = task（parent 显式控制）+ 自身只读调查，不再继承 parent 的历史对话。
- **风险**：行为级改动。先补注入行为测试（当前无测试覆盖这段注入），确认删掉后 delegate 相关测试（`test_delegate_child_is_read_only`、`test_delegate_uses_child_agent`）仍绿。

### M2. 修 Review Queue 并发写竞态（真实缺陷）
- **改**：`DurableMemoryReviewQueue._write`/`enqueue` 加进程内锁（模块级 `threading.Lock` 或实例锁），保证 read-modify-write 原子。
- **为何不做"parent 统一 enqueue 回流"**：child durable 已自动写共享队列（M2 修锁后无竞态），parent 查询即见——原提案的双重入队设计是多余架构，砍掉。
- **补**：child 候选的 `source_context` 已带 origin（`durable-promotion`），Review Queue 记录可溯源 child；无需额外字段。
- **效果**：多 worker + parent 并发写不丢记录；parent `/memory review` 可见 child 候选（记忆单向透明：parent 见 child）。

### M3. parent 监控 child（解决"随时监控状态和动向"）
- **改**：`WorkerManager` 新增 `status(runtime, task_id)` 查询（返回 item 的 status/updated_at/tool_steps + child trace.jsonl 尾部摘要）。
- **改**：`spawn` 后把 child run_dir 记进 item（当前只在 `_finish_task` 记）——使运行中可读 child trace。
- **改**：`_start_background` 时即 emit `worker_started` 事件上浮到 parent bus（已部分存在），补运行中 `worker_progress` 聚合信号（进度/错误/停因），**不**上浮全量 tool_executed（避免污染 parent 上下文——对应"child 上下文干净"的对偶面）。
- **效果**：parent（或 REPL `/agents`）可查询 child 实时状态与 trace 尾部；控制接口 `stop` 已存在。

### M4. trace 父子关联（审计链路简洁高效）
- **改**：`emit_trace` 增加 `parent_span_id` 字段（同 run 内线性链，顺序 span 或保留 uuid 但加 parent 链接）。
- **改**：child 构造时（`build_child_runtime`/`tool_delegate`）固化 `parent_run_id` + 当前 `parent_span_id` 到 child 实例；child 的 `run_started` 事件带上这两个字段。
  - **关键时序**：后台 worker 的 `ask()` 在线程里晚跑（parent 的 current_run_id 可能已清空），`parent_run_id`/`parent_span_id` **必须在 spawn 时固化**，不能 ask 时再读 parent。
- **删**：死代码 `core/runtime_events.py`、`core/runtime_secrets.py`（零 import）。
- **效果**：父子 trace 可关联（child trace 首事件带 parent_run_id/parent_span_id），审计链路可追溯且保持 JSONL 轻量。

---

## 三、不做的事（明确排除，避免为模仿而做）

- ❌ 不引入 `ChildContext` 统一抽象（write_scope/read_only/max_steps 已存在，重复封装无收益）。
- ❌ 不做 `context_allowlist` 信息注入白名单（与"child 只收 parent 控制"相悖；read_only 已限制写，读权限现状合理）。
- ❌ 不做"parent 统一 enqueue 回流"（child 已自动写共享队列，M2 修锁即可）。
- ❌ 不做集中式 trace DB、两阶段记忆管道、State DB 投影（JSONL + 磁盘读即所见已足够）。
- ❌ 不引入 Claude Code 式 memdir/CLAUDE.md 分层（现有 Review Queue 治理已满足"记忆需人工 accept"铁律）。

## 四、分阶段执行（每阶段独立走计划→审核→执行→验收）

| 阶段 | 内容 | 风险 |
|---|---|---|
| 1 | M2 并发写锁（真实缺陷，最优先） | 低 |
| 2 | M1 delegate 上下文干净（删 history 泄漏）+ 补行为测试 | 中（行为级） |
| 3 | M4 trace 父子关联 + 删死代码 | 低-中 |
| 4 | M3 parent 监控（status/trace_tail/进度上浮） | 中 |

## 五、红线

- 不破坏 Review Queue 治理：child 记忆进 parent 仍须人工 accept（现有机制保持）。
- 不削弱反粉饰测试（test_documented_snippets / test_docs_integrity）。
- 行为级改动（M1）必须补测试先行；trace 字段向后兼容（现消费方不破坏）。
- 每阶段以"ruff 0 error + 全量 pytest 绿 + 文档一致性"为门禁。
