# G2 方案：受阻后的确定性升级机制

> 依据：《RepoHarness 产品缺口交接》G2（已对当前 HEAD 复核确认仍存在）。
> 目标合同：第一次受阻时 Agent 先在现有授权和安全边界内换一种方法；如果安全替代仍被同一根因阻塞、且没有获得能改变判断的新信息，再询问用户。升级必须有**结构化 Runtime 状态**，不能只依赖 Prompt 或任意重试次数。

## 一、现状（已复核）

- `tool_executor.run_tool`：多个拒绝点（unknown_tool/invalid_arguments/repeated_identical_call/permission/policy），通过 `_metadata` 记录 `tool_error_code`/`tool_status`，回传错误文本给模型。
- `_record_runtime_reminder`（runtime.py:864）：累积 `runtime_reminders`（跨调用失败列表）——**这是已有的失败累积机制**。
- `repeated_tool_call`（runtime.py:923）：只查"连续两次完全相同"。
- `ask_user` 工具：模型可控，无失败自动触发。
- Engine 循环（engine.py:106-448）：工具失败→回传 error 文本→continue，无确定性升级分支。

## 二、目标合同（已确认）

```
动作 → Gate(允许/拒绝+Reason Code)
   拒绝 → 在已有权限内尝试安全替代 → 有新信息? → 是→继续
                                       → 否且同类根因持续 → ask_user(解释已尝试/共同根因/需用户决定)
   不可替代拒绝(缺授权/凭证/关键选择) → 直接 ask_user(不机械重试)
```

- 升级由 Runtime 保存结构化阻塞状态，模型可提出替代，但不能仅靠 Prompt 保证升级。
- "同类失败"不能只比较完整参数，应至少考虑错误类型、受影响资源和治理边界。
- "有效进展"≠更换命令字符串；需要新信息才算进展。
- 不设任意固定重试次数；用可解释规则 + 保守默认。

## 三、设计

### 1. 阻塞归并（复用 runtime_reminders，不新增状态结构）

**在现有 `runtime_reminders` 上做归并（双 Agent 审核裁决：不新增 `_blocked_state`，避免重复造轮子）**：

```python
# runtime_reminders 已累积每次失败:
#   {tool, status, tool_error_code, affected_paths, created_at}
# 每次 run 重置(engine.py:74 agent.runtime_reminders = [])
```

- **归并 key**：`(tool_error_code, resource_hint)`——resource_hint 从 `affected_paths`/`args` 提取（路径或资源名）。
- **归并纯函数** `merge_blocked_roots(reminders)`：遍历 reminders，按 key 计数，记录每次的 `tool`（即已尝试的替代）。
- **信息增量判定**：同 key 失败时，若出现**新的工具名** → 视为"尝试了替代"（有进展，延后升级）；若连续同 key 失败且工具名集合无新增 → 无新信息。

### 2. 升级触发（可解释规则，非任意重试数）

- **阈值**：同 key 失败 ≥ 2 次且该 key 的工具名集合无新增 → 生成升级。
- **不可替代拒绝（基于真实 code）**：`tool_error_code` ∈ {`approval_denied`（缺授权）、`sandbox_read_only`（read_only 下本就不该执行）} → 第 1 次即可升级（无安全替代）。
  - **`unknown_tool` 不在此列**（模型拼错工具名，可自动修复，给替代机会）。
  - `tool_not_allowed`/`plan_mode_tool_not_allowed`/`write_scope_mismatch` → 安全替代优先（换工具/换路径），≥2 次才升级。
- **升级内容（结构化）**：`{attempts: [...], root_cause: tool_error_code, resource: resource_hint, question: <建议问题>}`。

### 3. 升级动作（确定性打断 vs 记录上浮）

**核心裁决（双 Agent）：升级不能靠"注入 prompt_metadata 引导模型"——那是 no-op（metadata 不进模型 prompt 文本）且仍依赖模型。** 升级动作是：

- **有 `ask_user_callback` 时（交互场景）**：runtime **直接同步调用 `ask_user_callback(question, choices)`** 并消费答案——保证用户被询问（确定性升级），答案作为 user 消息回历史。
- **无 `ask_user_callback` / worker / 非交互场景**：**不打断**——升级对象写入 `session_event_bus.emit("blocked_upgrade", ...)` + trace `blocked_upgrade` 事件，留给上层处理（避免挂起）。
- **降级策略（用户已确认）**：有 callback 就确定性打断；无 callback 就记录上浮。

### 4. 安全边界

- 升级**不扩大权限**：ask_user 回答只作为用户指示，不自动提升 tool 权限。
- 不削弱现有拒绝（permission/policy/sandbox 的拒绝语义不变）。
- 不改变 `repeated_tool_call` 现有行为（保留，新增机制是"同类归并"更粗的 key）。
- **防重入**：同一 run 内同一 key 只升级一次（upgraded 集合），避免反复打断。

## 四、最小改动范围

1. `runtime.py`：
   - 新增 `merge_blocked_roots(reminders)` 纯函数（或模块级）。
   - 新增 `evaluate_blocked_state()`：基于 `runtime_reminders` 判定升级条件，返回升级对象或 None。
   - 新增 `upgrade_to_user(question, choices)`：有 callback 时同步调用并 record 答案；无 callback 时 emit `blocked_upgrade` 事件 + trace。
2. `engine.py`：tool 失败后调用 `evaluate_blocked_state()`；触发时调用 `upgrade_to_user`。
3. `engine_helpers.py`：`execute_tool_payload` 拿到失败元数据（`tool_error_code`/`tool_status`）后，为归并提供数据（reminders 已由 `_record_runtime_reminder` 累积，无需额外记录）。

## 五、失败测试计划（先补测试再实现）

新增 `tests/test_blocked_escalation.py`：

1. `test_first_tool_failure_does_not_upgrade`：第一次失败不升级（继续运行）。
2. `test_same_root_cause_repeated_upgrades`：同 key 失败 ≥2 次且无新信息 → 升级。
3. `test_alternative_tool_counts_as_progress`：尝试不同工具（安全替代）→ 延后升级（不触发）。
4. `test_irreplaceable_denial_upgrades_immediately`：`approval_denied`（缺授权）→ 第 1 次即升级。
5. `test_unknown_tool_is_not_immediate_upgrade`：`unknown_tool` 不第 1 次升级（给替代机会）。
6. `test_upgrade_contains_attempts_and_root_cause`：升级对象含 attempts/root_cause/resource/question。
7. `test_no_duplicate_upgrade_for_same_root`：同一 run 同 key 不重复升级。
8. `test_upgrade_calls_ask_user_callback_when_present`：**有 callback 时被实际调用并收到答案**（行为断言，非 metadata 字段）。
9. `test_upgrade_without_callback_emits_event_not_block`：无 callback 时 emit `blocked_upgrade` 事件 + trace，不打断。
10. `test_security_denial_not_weakened`：permission/policy 拒绝语义不变（现有安全测试仍绿）。

## 六、边界与红线

- 不重写控制循环（G2 文档明确）。
- 不设任意固定重试次数；升级规则可解释、阈值保守默认。
- 升级不扩大权限、不绕过拒绝。
- 不削弱反粉饰测试；不改变 `repeated_tool_call` 现有行为。
- 测试只测行为（升级触发/内容/注入），不锁死内部数据结构形状。
