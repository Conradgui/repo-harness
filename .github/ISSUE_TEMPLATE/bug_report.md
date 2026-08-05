---
name: Bug report
about: 报告一个可复现的问题
title: "[bug] "
labels: bug
assignees: ''

---

## 描述问题

请用一两句话描述发生了什么，以及你期望发生什么。

## 复现步骤

1. 运行命令/环境：
2. 操作步骤：
3. 观察到的结果：

## 期望行为

## 环境

- 操作系统（Windows / macOS / Linux，含版本）：
- Python 版本：
- 安装方式（`uv sync` / `pip install -e .` / 其他）：
- provider 与模型（如适用）：

## 最小复现（可选但强烈建议）

提供一个最小可复现的输入，或用 `FakeModelClient` 风格的 scripted 场景。项目强调行为测试（ADR-003）与可复现交付（ADR-006），能复现的问题才可能被修复。

## 附加信息

- 相关日志 / trace（脱敏后）：
- 是否检查过 `.repo-harness/` 下的 `trace.jsonl` / `task_state.json`：

> 安全相关请走 [SECURITY.md](../../SECURITY.md) 的私有上报渠道，不要在公开 issue 中披露。
