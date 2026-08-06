# G1 方案：运行结束与结果验证状态拆分

> 依据：《RepoHarness 产品缺口交接》G1（基于 main@531e02e，已对当前 HEAD 复核确认仍存在）。
> 目标合同：`run_status`（控制循环如何结束）与 `verification_status`（验收执行到何种程度）独立；只有 `run_status=completed ∧ verification_status=passed` 才算 verified outcome。

## 一、当前状态流（已复核）

```
模型 <final> → engine.py:387 task_state.finish_success(final)
             → task_state.py:100 status=completed, stop_reason=final_answer_returned
             → engine.py:391 _finalize_runtime_evidence(task_state)
             → runtime.py:934 verifier_suggestions = runtime_evidence.verifier_suggestions(root)  # 仅是"建议"列表
             → report.json / task_state.json 只含 status/stop_reason/verifier_suggestions
```

**问题**：`completed` 同时承载"控制循环正常结束"和"结果已验证"两个含义；`verifier_suggestions` 是建议快照，从未记录是否执行、结果如何。

## 二、目标决策表（run_status × verification_status）

| run_status | verification_status | 对外语义 | 可声明 |
|---|---|---|---|
| running | not_run | 运行中 | — |
| completed | not_run | 已结束回答，未执行验证（解释/调查/规划类任务） | answered only |
| completed | partial | 已结束回答，验证部分执行 | answered only |
| completed | failed | 已结束回答，验证失败 | answered only（文案不得出现 verified/tests passed） |
| completed | passed | 已结束回答，验证通过 | **verified outcome** |
| stopped | not_run | 被用户/预算中止，未验证 | — |
| failed | any | 模型错误/持久化错误等失败 | — |

**设计边界**：
- 不要求所有任务跑测试；无验证计划时 `verification_status` 保持 `not_run`，不伪装 `passed`。
- 不把 `<final>` 或模型自评当作验证信号。
- 不把 `verifier_suggestions` 的存在当作已执行。
- 不做综合质量分；两状态独立可解释。
- Auto Issue Fix 可消费本状态合同，但不反向污染通用 Runtime。

## 三、最小改动范围

### 1. `task_state.py` 新增字段与常量

```python
VERIFICATION_NOT_RUN = "not_run"
VERIFICATION_PASSED = "passed"
VERIFICATION_FAILED = "failed"
VERIFICATION_PARTIAL = "partial"

# TaskState dataclass 新增:
verification_status: str = VERIFICATION_NOT_RUN
# 记录验证证据(实际命令/检查器结果),非建议列表:
verification_evidence: list = field(default_factory=list)
```

- `finish_success()` **保持** `status=completed`（这是 run_status 语义），但**不写** `verification_status=passed`——它仍为 `not_run`。
- 新增 `mark_verification(status, evidence)` 方法。
- `to_dict`/`from_dict` 增加两字段（向后兼容：旧 dict 缺失时默认 `not_run`）。

### 2. `engine.py` final 路径（最小侵入）

`task_state.finish_success(final)` 之后**不自动**置验证状态。`_finalize_runtime_evidence` 生成 `verifier_suggestions` 后，**保持 `verification_status=not_run`**——因为建议≠执行。

### 3. 激活路径：在 Auto Issue Fix 中接入（复用现有执行栈）

**不新建 `run_verifier_commands` 死函数**（双 Agent 审核裁决：与现有执行器重复且无调用者）。复用 `repo_harness/auto_issue_fix/workspace.py` 已有的成熟执行栈：

- `infer_test_commands(repo_root)`：跨 9 语言生态的验证计划检测（pytest/npm test/go test/cargo test/mvn test/gradle test/dotnet test/rspec/ctest）。
- `run_test_commands(commands, cwd, log_path)`：执行并产出 `{command, status, returncode}` 结构化结果。

**Auto Issue Fix runner 的接入**：在 `run_live_auto_issue_fix` 的测试阶段（fix turn 后、commit 前），将测试结果写入通用 Runtime 的 `verification_evidence` 并调用 `mark_verification(passed/failed/partial, evidence)`：

- 全部测试命令 returncode 0 → `passed`
- 有失败 → `failed`
- 无推断命令但有用户显式提供 → 按其结果
- 无命令可推断 → `not_run`（不伪装）

**通用 Runtime 行为**：final 路径**不自动跑测试**（避免隐式副作用），`verification_status` 保持 `not_run`——诚实暴露"未验证"，阻断 completed 冒充 verified。Auto Issue Fix 是真实消费方，让字段真正生效。

### 4. `runtime.py build_report` 与对外文案

- `build_report` 增加 `run_status`（= task_state.status 别名）与 `verification_status`、`verification_evidence`。
- **对外摘要文案**：当 `verification_status != passed` 时，禁止出现 "verified" / "tests passed" / 等价确定性主张（在展示层收敛，不靠模型自觉）。
- `task_state.json` / `report.json` 同时含两字段。

### 5. 历史数据兼容

- `TaskState.from_dict` 缺失 `verification_status`/`verification_evidence` 时默认 `not_run`/`[]`（老 task_state 恢复不崩）。
- **checkpoint schema 不 bump**（双 Agent 审核裁决）：`checkpoint_builder.build_checkpoint` 产出的 checkpoint dict **不包含 verification 字段**（verification 属于 TaskState，两者是独立工件）；`evaluate_resume_state`（runtime.py:320）对 schema 严格相等校验，bump 会让历史 v1 checkpoint 全判 schema-mismatch。保持 `phase1-v1` 不动，verification 字段是 TaskState 的可选增量。
- `from_session` 恢复旧 session 时，旧 task_state 无新字段 → 默认 not_run，不破坏恢复。

## 四、失败测试计划（先补测试再实现）

新增 `tests/test_run_verification_status.py`：

1. `test_final_does_not_mark_verification_passed`：`<final>` 后 `status==completed` 但 `verification_status==not_run`。
2. `test_verification_status_not_run_for_explanation_task`：无测试目录的仓库，final 后 not_run。
3. `test_mark_verification_passed_records_evidence`：`mark_verification(passed, evidence)` 后 `verification_status==passed`，report 含 evidence。
4. `test_verification_failed_does_not_claim_verified`：失败后 `verification_status==failed`，report JSON 不含 "verified"。
5. `test_old_task_state_dict_migrates_to_not_run`：无 verification 字段的旧 dict → `from_dict` 默认 not_run。
6. `test_partial_verification`：部分命令成功 → partial。
7. `test_auto_issue_fix_test_results_write_verification_evidence`：Auto Issue Fix 的测试阶段（复用 `infer_test_commands` + `run_test_commands`）跑完临时脚本后，`verification_evidence` 被写入且 `verification_status` 正确置位（passed/failed）——**验证激活路径真实可达**。
8. `test_completed_not_run_has_no_verified_wording`：`completed ∧ not_run` 时 report 文案不含 verified/tests passed（决策表第 2 行）。

> 说明：不测 `run_verifier_commands`（已放弃该死函数）；不测 checkpoint schema v1 migration（checkpoint 不承载 verification 字段，无需 bump）。

## 五、边界与红线

- **不改变** `status`/`stop_reason` 既有语义（run_status 的载体），避免破坏大量既有断言（test_task_state.py:32 等仍成立）。
- **不自动执行测试**：G1 第一阶段不引入隐式跑测试副作用（`run_verifier_commands` 是显式能力，不默认调用）。
- 不引入综合质量分、不要求所有任务验证。
- 不削弱反粉饰测试；E1 已修复不受影响。
- `verification_status` 是新增字段，不是对 `status` 的重命名——老消费方读 `status` 仍工作。

## 六、待确认

1. 是否接受"第一阶段只做状态拆分，`run_verifier_commands` 作为可选项"？
2. `verification_evidence` 的结构是否够（command/returncode/passed/output_summary）？
3. checkpoint schema bump 到 v2 是否可接受（需 v1 兼容读入）？
