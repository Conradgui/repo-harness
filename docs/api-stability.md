# API 稳定性

本文档定义 repo-harness 的 public API 边界、稳定性承诺与弃用策略。项目处于 `0.x` 开发期，本文档描述的是**当前边界**，随发布迭代演进。

## 三个入口

| 入口 | 说明 | 稳定面 |
|---|---|---|
| `repo-harness`（CLI） | `[project.scripts]` 声明的控制台脚本，入口 `repo_harness.cli:main` | CLI 命令与 flag 是面向用户的稳定面；`--tui` 已弃用（见下） |
| `python -m repo_harness` | 模块入口，转发到同一 `main()` | 与 CLI 一致 |
| `from repo_harness import RepoHarness` | 库入口，编程方式驱动 agent | 核心稳定面 |

## 库 public API（`repo_harness/__init__.py` 的 `__all__`）

当前 `__all__` 导出以下符号，按稳定度分类：

### 稳定（作为库使用时应依赖的面）

- `RepoHarness` — 核心类，`ask()` / `from_session()` / `evaluate_resume_state()` 等为主要接口。
- `SessionStore`、`WorkspaceContext` — 会话与工作区抽象。
- 各 `*ModelClient`（`OpenAICompatibleModelClient` / `ChatCompletionsCompatibleModelClient` / `AnthropicCompatibleModelClient` / `OllamaModelClient` / `FakeModelClient`）— model client 契约。

### CLI 构造器（可用，但语义上属于 CLI 层）

- `main` — CLI 入口，库代码不应依赖它。
- `build_agent` / `build_arg_parser` / `build_welcome` — 为 CLI/REPL 装配服务的构造器，暴露在 `__all__` 主要出于测试与脚本复用。**在 `1.0.0` 前可能移入 `_cli` 命名空间或调整签名**；当前阶段建议库使用者只依赖 `RepoHarness` 及其模型/会话抽象。

## 0.x 兼容预期

- `0.x` 阶段不承诺 semver 严格向后兼容，但**任何破坏性变更必须在 CHANGELOG 显著标注**，并在可行时提供迁移提示。
- public API 的移除遵循弃用流程（见下），避免无声破坏。
- 内部模块（`core/*`、`features/*`、`auto_issue_fix/*`、`evaluation/*`）不是稳定面，不构成兼容承诺；但同一大版本内不应无故破坏。

## 弃用策略

参考既有先例：`--tui` 通过 `argparse.SUPPRESS` 隐藏并触发 `DeprecationWarning`，自动降级为 `--repl`。

- 弃用一个符号/flag：保留行为但触发 `DeprecationWarning`（`stacklevel=2`），至少保留一个大版本。
- 移除：在 CHANGELOG 记录，并附迁移说明。
- 重大破坏性变更：新增 ADR 说明理由，并提前一个版本预告。

## 版本号与稳定性的关系

版本号（`pyproject.toml` 的 `version`）由**对外发布的内容量级与 API 稳定性**决定，与内部迭代代号（v1–v7）无关。发布流程见根目录 [RELEASING.md](../RELEASING.md)。
