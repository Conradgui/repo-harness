# E2：Auto Issue Fix 真实闭环 dogfood 复盘

> 目的：闭合产品缺口 E2（Auto Issue Fix 缺少公开真实闭环产物）。本文是**结果性与复盘性资料**；完整过程证据见同目录 `e2-dogfood-evidence/`（28 个文件）。
> 记录日期：2026-08-06。运行环境：Windows 11 / Python 3.13 / deepseek provider。

## 一、结论

**Auto Issue Fix 的真实执行路径（live 闭环）已端到端跑通**：读取 issue → clone → 基线测试（复现失败）→ 真实 provider 修复 → 修复后测试通过 → commit → push → 生成 draft PR（模拟），并产出完整证据包。`verification_status=passed` 且 8 个自动审查门全部 `pass`。

**诚实边界**：
- 目标仓库是**本地模拟的第三方仓库**（`pricing-helper`，含真实可复现 bug + 失败测试），非真实 GitHub 上游。因此 push/PR 是**本地模拟**（`LocalBackend`），未对任何第三方仓库产生网络副作用。
- 一次跑通**不等于**长期稳定性或外部用户价值（产品文档 §7.2 明确此边界）。
- 这是"真实执行路径"证据（真实 provider、真实修复、真实测试、真实 gate），不是"真实 GitHub 协作"证据。

## 二、Fixture（模拟第三方仓库）

| 项 | 值 |
|---|---|
| 仓库 | `local/fixture`（`pricing-helper`，仅 4 个 tracked 文件） |
| 源码 | `pricing.py`（2 个刻意植入的 bug） |
| 测试 | `test_pricing.py`（4 个用例，基线 2 failed） |
| issue | `#1`：批量折扣在恰好 5 件时不生效；总价截断而非四舍五入 |

**两个 bug**（基线测试复现）：
1. `apply_bulk_discount` 用 `> 5` 而非 `>= 5`，恰好 5 件不打折。
2. `calculate_total` 用 `int(total)` 而非 `round(total)`，99.99 截断为 99。

## 三、运行过程（真实执行）

1. **issue 读取**：`LocalBackend.issue_view` 读本地 issue 描述。
2. **clone**：`git clone` 本地 fixture 到唯一 workdir（`repo-harness-auto-issue-fix-1` 分支）。
3. **基线测试**：`python -m pytest test_pricing.py -q` → **2 failed**（复现 bug）。
4. **修复 turn**（真实 deepseek provider）：agent 读取源码/测试 → `patch_file` 两次 → 自我验证测试通过。
5. **修复后测试**：`python -m pytest test_pricing.py -q` → **passed（returncode 0）**。
6. **审查门**：8 个 gate（task/plan/context/diff/tests/security/pr-readiness/maintainer-trust）全部 `pass`。
7. **commit**：`8362117`（真实 git commit）。
8. **push**：本地 bare 仓库充当 fork，`git push fork` 本地成功。
9. **draft PR**：`LocalBackend.create_pr` 生成模拟 PR URL（本地记录，不碰 GitHub）。

## 四、结果证据（28 文件，见 `e2-dogfood-evidence/`）

| 文件 | 内容 |
|---|---|
| `issue.json` | issue 快照 |
| `baseline-repro.log` | 基线失败复现（2 failed） |
| `fix-run.log` | 修复总结（`>= 5` 与 `round()`） |
| `test-after-fix.log` | 修复后测试（passed） |
| `git-diff.patch` | 真实 diff（仅 `pricing.py`，2 处修复） |
| `run-record.json/md` | 运行记录（status=completed, verification=passed, changed_paths=[pricing.py]） |
| `reviews/review-*.{json,md}` | 8 个自动审查门（全 pass） |
| `decision-log.jsonl` | 决策日志 |
| `pr-body.md` | 维护者友好 PR 描述（六段式，占位符脱敏） |
| `pr-url.txt` | 模拟 PR URL |
| `checkpoint.json` | 阶段检查点 |

**关键指标**：status=`completed`；verification_status=`passed`；baseline_status=`failed`→tests passed；changed_files=`1`（仅源码，无无关改动）；review gates `block=0, pass=8`。

## 五、修复内容验证（复盘确认）

workdir 中 `pricing.py` 实际落盘：
- `return int(total)` → `return round(total)` ✓
- `if len(items) > 5` → `if len(items) >= 5` ✓

修复**真实写入文件**（非模型声称），测试真实通过。`changed_paths=[pricing.py]` 证明改动精确、无范围蔓延。

## 六、与 G1/G2/G3 的协同验证

- **G1**：`verification_status=passed` 在真实流程中生效——测试实际运行且通过，非 `<final>` 自动标记（对比 baseline `failed`）。
- **G2**：本次无阻塞升级触发（deepseek 直接成功修复）；升级机制由 `tests/test_blocked_escalation.py` 覆盖。
- **G3**：issue/fix 全英文，未触发 canonical 逻辑。

## 七、局限与后续

**局限**：
1. 目标是本地模拟仓库，非真实 GitHub 上游——真实 fork/draft PR 仍需用户维护权限的仓库。
2. 单次运行，样本量 1；不同 provider/bug 类型下稳定性未知。
3. 修复质量依赖模型能力；审查门只验证"diff 范围 + 测试通过"，不证明"修复语义正确"（需人审）。

**后续**：
- 若需"真实 GitHub 协作"证据：在用户有维护权限的受控仓库上跑一次（用户提供仓库 + issue）。
- 可用更多 fixture（不同语言/框架/错误类型）扩展 dogfood 样本。
- 建议将本 fixture 流程固化为 `scripts/run_e2_dogfood.py`（当前为临时脚本），便于回归。

## 八、红线遵守

- ✅ 未对任何第三方 GitHub 仓库 push/PR/产生网络副作用。
- ✅ 证据脱敏（占位符 `<repo>`/`<evidence_dir>`；`pr-body.md` 无本地路径）。
- ✅ 诚实标注"模拟 PR"，未声称真实 GitHub 闭环。
- ✅ 一次跑通 ≠ 长期稳定（未夸大）。
