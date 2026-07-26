# ADR-001 · 放弃 codex 分支，从 main 重建

**状态**：已执行
**日期**：2026-07-27
**影响范围**：51 个 commit、15,376 行改动

---

## 处境

`codex/repo-harness-phase1-security-kernel` 领先 `main` 51 个 commit。开发者的直觉是"越迭代越乱、无从下手"。需要决定：在这个分支上继续修，还是放弃它。

## 观察到的事实

**投入构成严重失衡**：

| 类别 | 新增行数 | 占比 |
|---|---|---|
| 文档 | +6,374 | 41% |
| 测试 | +5,612 | 36% |
| 源码 | +2,765 | 18% |

77% 的产出是文档和测试。而 18% 的源码里，新增的 `repo_harness/security/`（isolation 268 + authorization 123 + staging 55）本身就是封锁机制。

**核心能力被四层封锁，最底层实现已删除**：

| 层 | 位置 | 行为 |
|---|---|---|
| 1 | `tools/__init__.py:553` | `tool_write_file` / `tool_patch_file` 函数体被删，只剩 `raise` |
| 2 | `core/tool_profiles.py:17` | `ToolSetProfile.__post_init__` 从所有 profile 剥离写工具 |
| 3 | `permissions.py:35` | 权限检查第一行无条件 deny |
| 4 | `auto_issue_fix/runner.py:167` | `_block_on_phase0` |

用同一个权限探针在两个分支上跑同一组场景：`main` 允许 2/6，codex 分支允许 **0/6**。该分支上的 agent 无法修改任何文件。

**分支测试是红的**：15 failed / 728 passed，其中 10 个是该分支自己引入的。最新 commit `2d62a8c` 就引入了 3 个。

**迭代模式本身有问题**——commit 历史显示的收尾方式是：

```text
写计划文档 → 实现 → 发现风险 → 删掉实现加 gate → 写文档说明 gate → 加测试断言文档写了 gate
```

历史里还有连续三个 Revert 撤销刚做完的三个 commit。

## 考虑过的选项

**A · 在 codex 分支上解锁**
需要：恢复被删的实现、拆四层封锁、修 15 个失败测试、拆掉一个「代码不许变短」的测试、处理 state store 回归。**实质等于把 main 已有的代码重写一遍**，同时继续背着 6,374 行文档沉积。

**B · 放弃分支，从 main 重新走**
main 的权限分层完好、写入实现完整、测试基本可用。代价是丢掉分支上两个真实修复。

**C · 从 main 拉分支，cherry-pick 有价值的 commit**
理论上兼顾两者。

## 决策

**选 C 的变体：从 main 重建，有价值的修复以手工补丁移植，而不是 cherry-pick。**

对 51 个 commit 做了完整依赖图分析和 dry-run cherry-pick 实测，结论是 cherry-pick 不可行：

- 分支底座 `8eaf1d5` 是一个 15,376 行的巨型 commit，重写了 `tests/conftest.py`，所有后续测试类 commit 都依赖它
- 保留它 = 一次性吞下 15,000 行，与瘦身目标直接冲突
- 丢弃它 = 后续 commit 全部无法 cherry-pick

因此把 rg 参数注入修复以补丁形式直接打到 main 上。

**codex 分支不删除**，作为零件仓库保留。

## 后来证明

修复 rg 问题时发现 main 上的缺口比分支上更大——除了缺 `--` 终止符，还缺 `--fixed-strings`，而且 Python fallback 与 rg 路径语义完全不一致。手工移植反而促成了一个更完整的修复，cherry-pick 只会带来那一行。

## 教训

诊断阶段我曾说「改动集中在 `permissions.py` 一个文件，风险可控」。**错得离谱**——实际是四层，最底层实现已被删除，只改那一个文件毫无作用。

问题出在基于单点发现就下范围结论。后续改为：下范围结论前先做穷举扫描（AST 遍历、符号级引用检查），而不是 grep 到几个就算数。
