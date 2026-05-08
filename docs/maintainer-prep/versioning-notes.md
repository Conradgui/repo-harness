# 版本管理记录

## 文档说明

这份文档用于记录维护者资料和关键仓库状态的版本管理规则。它帮助维护者知道哪些记录可以追加、哪些基线不能改写、哪些 tag 或提交可用于回滚。

本文不是 Git 教程，也不是完整提交历史。具体代码变更仍以 Git log 为准；这里记录的是维护者需要主动记住的版本边界和文档维护规则。

## 更新规则

- 每个关键基线、归档点或文档管理规则变化都新增一个日期小节。
- 不改写已经发布或已经归档的 tag 指向。
- 如果后续切换主分支、重命名项目或改变远程仓库，应新增记录说明新基线。
- 文档调整使用独立 `docs:` 提交，避免和代码修复混在一起。

## 版本记录

### 2026-05-03：RepoHarness 全量重命名基线

#### 当前公开接口

- Python 包名：`repo_harness`
- CLI 命令：`repo-harness`
- 模块入口：`python -m repo_harness`
- 本地状态目录：`.repo-harness/`

#### 迁移规则

- 首次启动时，如果仓库根目录存在历史 `.pico/`，RepoHarness 只复制 `.repo-harness/` 中缺失的文件。
- 迁移不会覆盖已有 `.repo-harness/` 文件，也不会删除 `.pico/`。
- 旧 `pico` CLI 和 `python -m pico` 不再作为支持入口维护。

#### Agent 指令文件规则

- `AGENTS.md` 是可选仓库级指令文件，不是运行必需文件。
- 本次重命名不新增 `AGENTS.md` 或 `AGENT.md`。
- 如果未来需要添加仓库级 agent 规则，优先使用现有代码约定的复数文件名 `AGENTS.md`。

### 2026-05-03：重命名前 GitHub 存档基线

#### 基线信息

- 工作分支：`<archive-work-branch>`
- GitHub 存档 remote：`<archive-remote>`
- GitHub 存档仓库：`https://github.com/<owner>/<repo-archive>.git`
- 重命名前基线 tag：`archive-before-repoharness-rename-20260503`
- tag 指向提交：`9d78e0f49cf147cb671531e05251d4d0b43220d3`

#### 管理规则

- 后续如果推进 `RepoHarness` 全量重命名，应基于该 tag 或当前分支创建新提交，不要改写已有存档 tag。
- 如果需要回滚到重命名前状态，优先使用该 tag。

### 2026-05-03：维护者文档管理规则

#### 文档分层

- `changelog-draft.md`：发布说明草案，按日期维护待发布变更；发版时再整理到正式 changelog。
- `issue-triage.md`：问题归因记录，按日期追加排查结论。
- `patch-summary.md`：修复摘要记录，按日期追加修复批次。
- `windows-compatibility.md`：Windows 兼容性记录，按日期追加平台相关适配。
- `project-study-sop.md`：项目学习 SOP，按日期记录入口、路径或阅读方法的变化。
- `README.md`：本目录索引；新增维护者文档时必须同步更新。

#### 提交分组建议

1. 兼容性修复：`fix: ...`
2. 测试和验证：`test: ...`
3. 文档和维护者资料：`docs: ...`
4. CI 或工程配置：`ci: ...`
5. 品牌或包名重命名：`refactor: ...`

#### 评审清单

- 执行 `uv run ruff check .`。
- 执行 `uv run pytest -q`。
- 如果只改文档，可以说明未跑全量测试的原因；涉及命令示例、包名、路径或测试保护文档时仍建议跑相关测试。
- 如果条件允许，分别在 Windows CMD、Windows PowerShell 和类 Unix shell 中确认入口命令。

#### 对外表述口径

- Windows 是复现环境，不是根因本身。
- 这批工作应描述为跨平台兼容性加固、benchmark 可移植性修复、可复现性稳定化和维护者文档补强。
- 如果进入 `RepoHarness` 重命名阶段，应单独描述为破坏性品牌和接口重命名，不要和 Windows 兼容性修复混在一个 changelog 条目里。
