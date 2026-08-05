---
name: Feature request
about: 提议一个新能力或改进
title: "[feat] "
labels: enhancement
assignees: ''

---

## 要解决的问题

你想解决什么痛点？请描述场景，而不是直接给方案。

## 你设想的方案

描述你期望的行为。注意项目遵循若干长期约束，见 [CONTRIBUTING.md](../../CONTRIBUTING.md)：

- 行为测试优先（ADR-003）：新功能必须伴随能抓住 bug 的测试。
- 安全边界用开关而非删除（ADR-002）。
- 文档数字必须可复现（ADR-006）。
- 长期记忆必须经过 Review Queue，任何能力不得直接写 durable topics。

## 备选方案（可选）

你考虑过的其他做法。

## 影响面

- 涉及 CLI / 库 API / REPL / Auto Issue Fix / memory / 安全边界 / 文档 哪些方面？
- 是否会改变既有行为？如果会，说明理由（项目优先保持向后兼容，参考 `--tui` 的弃用先例）。
