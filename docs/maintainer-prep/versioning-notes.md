# 版本管理说明

这份文档记录维护者资料的版本管理约定。它的读者包括当前维护者本人和未来维护者；目标是让 `docs/maintainer-prep/` 下的阶段记录可追溯、可继续更新，而不是一次性写完后失去上下文。

## 当前基线

- 工作分支：`codex/pico/cross-platform-hardening`
- GitHub 存档 remote：`github`
- GitHub 存档仓库：`https://github.com/Conradgui/repo-harness-test-.git`
- 重命名前基线 tag：`archive-before-repoharness-rename-20260503`
- tag 指向提交：`9d78e0f49cf147cb671531e05251d4d0b43220d3`

后续如果推进 `RepoHarness` 全量重命名，应先基于这个 tag 或当前分支创建新提交，不要改写已有存档 tag。

## 文档分层

- `changelog-draft.md`：发布说明草案，按“未发布”维护；发版时再整理到正式 changelog。
- `issue-triage.md`：问题归因记录，主要记录判断口径；新增问题时追加分类，不覆盖旧判断。
- `patch-summary.md`：修复摘要，记录“为什么这样改”；新增修复时追加新小节，历史路径保留为当时版本事实。
- `windows-compatibility.md`：Windows 适配边界说明；如果后续改变兼容策略，需要新增“变更记录”而不是只改旧结论。
- `project-study-sop.md`：项目阅读 SOP；项目主入口或包名变化时需要同步更新命令和路径。
- `README.md`：本目录索引；新增维护者文档时必须同步更新。

## 更新规则

- 每次阶段性文档调整都单独提交，commit message 使用 `docs:` 前缀。
- 不把“历史事实”改写成“当前事实”。如果路径、命令、品牌名后续变化，应增加版本口径说明。
- 涉及公开命令、包名、本地状态目录、benchmark 口径的变更，需要同时检查 README、getting-started、SOP、Windows 说明和测试断言。
- 本地私有材料放入 `docs/local/`，不要混入维护者公开文档。
- 如果文档引用某个提交或 tag，应写出完整哈希或明确 tag 名，避免之后无法定位。

## 提交分组建议

Windows 适配和维护者文档已经按主题拆分为多次提交。后续继续修改时仍按主题拆分：

1. 兼容性修复：`fix: ...`
2. 测试和验证：`test: ...`
3. 文档和维护者资料：`docs: ...`
4. CI 或工程配置：`ci: ...`
5. 品牌或包名重命名：`refactor: ...`

## 评审清单

- 执行 `uv run ruff check .`。
- 执行 `uv run pytest -q`。
- 如果只改文档，可以说明未跑测试的原因，但涉及命令示例、包名、路径或测试保护文档时仍建议跑相关测试。
- 如果条件允许，分别在 Windows CMD、Windows PowerShell 和类 Unix shell 中确认入口命令。

## 对外表述口径

- Windows 是复现环境，不是根因本身。
- 这批工作应描述为跨平台兼容性加固、benchmark 可移植性修复、可复现性稳定化和维护者文档补强。
- 如果进入 `RepoHarness` 重命名阶段，应单独描述为破坏性品牌和接口重命名，不要和 Windows 兼容性修复混在一个 changelog 条目里。
