# 维护者提交准备

## 文档说明

这个目录用于集中存放维护者在项目验证、问题归因、修复复盘、版本管理和提交准备过程中沉淀的资料。它同时服务当前维护者本人和未来可能接手项目的维护者。

这里的文档不是一次性说明。凡是记录性质的内容，都应采用“文档说明 + 更新规则 + 按日期追加记录”的结构，避免把某一次修复写死成文档永久定义。

## 更新规则

- 新增维护者文档时，先在本 README 中补目录说明。
- 任何改变公开入口、CLI/REPL 命令、本地状态目录、持久化格式、记忆系统、运行工件或安全边界的代码更新，都必须同步检查 README、getting-started、architecture、review-pack 和 maintainer-prep 文档是否需要更新；如果变更涉及记忆系统，还必须检查 `memory-system-new-window-handoff.md` 是否需要同步。
- 文档同步是功能完成后的必需门禁。不能只完成代码和测试而跳过文档；如果判断某个文档不需要改，应在修复摘要或提交说明中写明原因。
- 阶段性文档变更使用独立 `docs:` 提交。
- 记录型文档以追加为主，历史记录中的路径、命令、包名和判断口径代表当时版本事实。
- 本地私有材料放入 `docs/local/`，不要混入可提交的维护者资料。

## 目录索引

- `issue-triage.md`：问题归因记录，按日期记录每次排查的环境触发条件、代码库根因和维护者判断口径。
- `patch-summary.md`：修复摘要记录，按日期记录每批修复的背景、涉及位置、处理方式、验证结果和后续注意。
- `changelog-draft.md`：待发布更新日志草案，按日期积累用户可读的变更说明。
- `versioning-notes.md`：版本管理记录，记录关键 Git 基线、存档 tag、文档管理规则和提交分组建议。
- `project-study-sop.md`：项目学习 SOP，按日期记录维护者理解项目的推荐路径。
- `windows-compatibility.md`：Windows 兼容性记录，按日期记录 Windows 适配策略、验证命令和已知边界。
- `memory-system-iteration-roadmap.md`：记忆系统迭代路线，记录 memory pack、记忆治理和后续记忆智能能力的边界与推进顺序。
- `memory-system-new-window-handoff.md`：记忆系统新窗口交接文档，作为后续维护窗口的快速上下文入口；README、getting-started、roadmap、patch-summary 或记忆系统能力更新时必须同步检查它是否需要更新。

## 2026-05-03：目录基线

本目录在 Windows 适配和工程化补强阶段形成，当前记录仍使用重命名前的 `pico` 包名、CLI 命令和 `.pico/` 状态目录。

后续如果执行 `RepoHarness` 全量重命名，应新增对应日期记录，并在各记录型文档中保留历史事实，不直接把旧记录改写成新品牌下的当前事实。

## 2026-05-05：文档同步门禁

Memory Pack v1 之后，维护者工作流增加一个硬性收尾步骤：代码、测试和 CLI 验证完成后，必须复盘文档体系是否同步。

最低检查清单：

- README 是否覆盖新的用户可见能力和快速入口。
- `docs/getting-started.md` 是否覆盖首次使用者需要知道的命令、风险和恢复方式。
- `docs/architecture/agent-harness-v1-overview.md` 或 review-pack 是否需要记录新的状态目录、运行工件或架构边界。
- `docs/maintainer-prep/*` 是否需要追加维护者决策、修复摘要、changelog 草案或后续路线。
- 如果更新 README、getting-started、memory roadmap、patch-summary 或任何记忆系统相关文档，必须同步检查 `docs/maintainer-prep/memory-system-new-window-handoff.md` 是否仍与当前事实一致。
- `memory-system-new-window-handoff.md` 的“当前状态”和“下一步”必须与 roadmap 保持一致，不能把已完成能力继续列为 future work。
- 测试是否需要保护关键文档资产，避免文档再次落后于代码。
