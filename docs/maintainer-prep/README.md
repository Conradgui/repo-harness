# 维护者提交准备

这个文件夹用于集中存放在 Windows 环境下验证仓库时发现的跨平台兼容性问题、工程硬化问题，以及后续向项目管理员提交贡献前所需的准备材料。

这些资料不是一次性说明文档，而是维护者持续更新的工作记录。每次阶段性修改都应进入 Git 历史；涉及版本口径、路径、命令或品牌名变化时，先更新 `versioning-notes.md`，再同步调整相关文档。

## 文件说明

- `issue-triage.md`：对每一类失败进行归因，区分是环境触发、代码库可移植性问题，还是仓库缺少必要资产。
- `patch-summary.md`：把已观察到的问题映射到具体代码位置、根因、修正建议和修正理由。
- `changelog-draft.md`：为后续维护者接受变更后准备的更新日志草案。
- `versioning-notes.md`：为后续向上游提交修复准备的分支、提交、评审和交付建议。
- `project-study-sop.md`：给新维护者的项目阅读和验证 SOP，用测试反推主链路和核心设计。
- `windows-compatibility.md`：记录 Windows 适配边界、根因、验证命令和已知限制。

## 版本管理约定

- 文档变更使用独立 `docs:` 提交，避免和代码修复混在一起。
- `patch-summary.md` 和 `issue-triage.md` 以追加为主；如果后续路径或品牌名变化，保留旧版本事实，并新增说明当前口径。
- `changelog-draft.md` 只维护待发布内容；发版或重命名时再拆出正式 release note。
- 当前重命名前存档 tag 是 `archive-before-repoharness-rename-20260503`，详细口径见 `versioning-notes.md`。

## 适用范围

这些内容是面向项目维护者和贡献提交的准备材料，故意与产品文档以及测试依赖的文档分开存放，避免混淆。
