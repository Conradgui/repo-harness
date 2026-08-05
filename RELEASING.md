# 发布流程

本文件定义 repo-harness 如何从开发态走到发布态。当前项目尚未发布正式 release（版本 `0.1.0`），以下规则从首次发布起生效。

## 版本规则

- 遵循 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/)。
- `0.x` 阶段：`0.1.0` 起步。`0.x` 的 minor 递增表示新增能力或行为变化；`0.x.y` 的 patch 用于修复。
- 进入 `1.0.0` 之前，public API（`RepoHarness.ask()`、`repo-harness` CLI、`python -m repo_harness`）不应有破坏性移除；确有破坏性变更时，必须在 CHANGELOG 显著标注并考虑 bump minor。
- **文档迭代代号（v1–v7）不等于发布版本**。CHANGELOG 记录它们为开发史；版本号只由"对外发布的内容量级 + API 稳定性"决定，不由文档叙事决定。

## 发布步骤

1. **CHANGELOG**：把 `[Unreleased]` 下的内容归入新版本段，确认所有条目与代码一致（ADR-006：数字必须可由命令复算）。
2. **版本号**：更新 `pyproject.toml` 的 `version`，并同步确认 `repo_harness/memory_pack.py` 中 `_repo_harness_version()` 的包未安装回退值一致。
3. **门禁全绿**：
   ```bash
   uv run ruff check .        # 0 error
   uv run pytest tests/ -q    # 全绿
   uv run pytest tests/test_docs_integrity.py tests/test_documented_snippets.py -q
   python scripts/measure.py  # 产出交付文档引用的量化指标（如改动）
   ```
4. **打 tag**：`git tag v0.1.0`（tag 名与 pyproject version 对应，形如 `v<version>`），push tag。
5. **发布说明**：从 CHANGELOG 提取该版本条目作为 Release Notes；附加 `RunEvidence` / 交付验收产物（如有）。
6. **PyPI 发布**（首次发布时启用）：配置 Trusted Publishing 后，CI 在 tag push 时自动构建上传；发布前确认 `classifiers` / `[project.urls]` 完整。

## 发布纪律

- **绝不为了"看起来版本高"而改动版本号**。版本是工程事实，由发布历史决定。
- 每次发布必须能复现：从 tag checkout 后，门禁命令应全部通过。
- 发布后发现回归：优先在最新分支修复并记录到 CHANGELOG 的 Fixed 段，视严重度决定是否补发 patch。
