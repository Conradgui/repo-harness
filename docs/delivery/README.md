# 交付文档

分支 `release/optimized-v1` 的完整交付材料。

| 文档 | 内容 |
|---|---|
| [01-交付报告.md](01-交付报告.md) | 交付摘要、决策依据、缺陷修复、未处理问题清单 |
| [02-测试资料.md](02-测试资料.md) | 测试分层、设计决策、缺陷追踪、后续建议 |
| [03-面试资料包.md](03-面试资料包.md) | 岗位定位、能力证据、高频追问、简历条目 |
| [04-后续路线图.md](04-后续路线图.md) | 未完成项的方案与优先级 |
| [E2 dogfood 复盘](04-E2-dogfood-复盘.md) | Auto Issue Fix 真实闭环 dogfood 结果与复盘 |
| [E2 证据包](e2-dogfood-evidence/) | 28 个过程证据文件（issue/trace/diff/review gates） |
| [多 Agent 模拟用户验证](05-多Agent模拟用户验证复盘.md) | 多 Agent 模拟用户 + Terminal 执行 + 独立验证的复盘 |

决策记录见 [docs/decisions/](../decisions/README.md)。

## 快速验证

```bash
git checkout release/optimized-v1
uv sync
uv run ruff check .
uv run pytest tests/ -q
```

预期 `All checks passed`，测试全绿。

## 数字从哪来

交付文档里的核心量化指标由脚本产出，不手写：

```bash
python scripts/measure.py "$(git merge-base origin/main HEAD)"   # before 基线（优化分叉点）
python scripts/measure.py                                        # 当前
python scripts/permission_probe.py                               # 写入权限矩阵
```

`measure.py` 覆盖行数、文件数、ruff 错误数、`RepoHarness` 方法聚类、`Engine` 规模、被引用模块的行数、领先基线的提交数。它在无法解析 ruff 输出时**报错而非返回 0**——一个分不清「干净」和「跑挂了」的指标比没有更危险。

> 基线用 `git merge-base origin/main HEAD`（优化分叉点）而非浮动的 `origin/main`：优化合并回 main 后，`origin/main` 不再代表优化前状态，用它做基线会让所有 delta 塌缩为 0。merge-base 是不可变、可复算的分叉点。

理由见 [ADR-006](../decisions/006-交付数字必须可复现.md)——手写的数字在本项目里已经漂移过两轮。

## 提交列表

```bash
git log --oneline "$(git merge-base origin/main HEAD)"..HEAD
```

每个提交自包含，可单独 revert。
