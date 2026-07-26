# 交付文档

分支 `rebuild/trunk` 的完整交付材料。

| 文档 | 内容 |
|---|---|
| [01-交付报告.md](01-交付报告.md) | 交付摘要、决策依据、缺陷修复、未处理问题清单 |
| [02-测试资料.md](02-测试资料.md) | 测试分层、设计决策、缺陷追踪、后续建议 |
| [03-面试资料包.md](03-面试资料包.md) | 岗位定位、能力证据、高频追问、简历条目 |
| [04-后续路线图.md](04-后续路线图.md) | 未完成项的方案与优先级 |

架构与用户流程图为在线文档，见交付报告首节引用。

## 快速验证

```bash
git checkout rebuild/trunk
uv sync
uv run pytest tests/ -q
```

预期 `345 passed, 1 skipped`，约 150 秒。

## 本次交付的四个提交

```text
e294ac1  refactor: drop the benchmark and experiment machinery
365734f  test: replace prose and line-count assertions with integrity checks
46f34aa  fix: align the two search backends and harden the ripgrep invocation
69f4dfa  fix: decode subprocess output as UTF-8 instead of the system locale
```

每个提交自包含，可单独 revert。
