# 维护者文档入口

## 当前状态

RepoHarness 最终版 v3 能力完善已经合入 `main`。Auto Issue Fix 真实执行与 dry-run 预演是当前版本的同等级重要更新。维护目标是保持文档、测试和 release evidence 与实现一致，不再把已完成能力列为后续工作。

当前公开边界：

- CLI：`repo-harness`
- 模块入口：`python -m repo_harness`
- Python 包：`repo_harness`
- 本地状态目录：`.repo-harness/`
- 参考基线：参考仓库 v3 commit `91a7c17`
- Auto Issue Fix：`repo-harness auto-issue-fix` 和 `/auto-issue-fix` 当前提供真实执行与 dry-run 预演；普通 REPL 中 `/auto-issue-fix` 支持引导式输入，真实 PR 一律 draft。

不要恢复旧状态目录、旧配置文件、旧 CLI、旧截图或旧公共命名。

## 文档同步规则

- 文档同步是功能完成后的必需门禁。
- 代码改变公开入口、配置、provider、sandbox、skills、workers、TUI、evidence、memory 或 release gate 时，必须检查 README、getting-started、architecture、review-pack 和 maintainer-prep。新增 provider 时还必须覆盖配置优先级、环境变量、`/usage` 元数据和文档示例。
- README、getting-started、memory roadmap、patch-summary 必须和当前实现同步。
- Auto Issue Fix 变更还必须同步 `docs/auto-issue-fix-product-plan.md`、`docs/auto-issue-fix-implementation-plan.md`，并确认 README、getting-started、architecture 和 review-pack 准确区分真实执行和 `--dry-run` 预演。
- Auto Issue Fix 文档必须说明两种模式都经过自动审查门：`review-gated` 是自动审查后人工确认，`draft-auto` 是自动审查后减少人工暂停。
- Auto Issue Fix 文档必须默认推荐 `review-gated`，并说明所有模式的 patch、测试日志和 PR 描述都需要人工严格 review 和验证。
- 公开 `pr-body.md` 必须使用维护者友好的五段式模板，不能默认包含工具链、模型、实验记录、trace、benchmark、dogfood 或本地 evidence 说明。
- 任何 GitHub blocked / forbidden / permission denied / cannot perform action 结果都必须停止，不重试、不绕过、不换账号推进，只写 fallback 和复盘材料。
- 文档更新使用独立 `docs:` 提交，不和功能代码混在一个提交里。
- 当前说明以中文为主；历史事实可以保留 commit id，但不要让旧参考仓库成为当前产品主体。
- 文档不能绕过 Review Queue，不得写出“自动写 durable memory”的语义。
- 不能把已完成能力继续列为 future work；如需保留英文锚点，只能作为测试兼容或历史索引。

长期记忆治理固定为：

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

## 目录索引

- `repo-harness-v3-compat-status.md`：最终版功能状态和验证结果。
- `repo-harness-v3-compat-roadmap.md`：v3 能力完善路线和保留边界。
- `patch-summary.md`：维护者修复摘要。
- `changelog-draft.md`：面向发布说明的草稿。
- `versioning-notes.md`：分支、提交和文档提交规则。
- `memory-system-iteration-roadmap.md`：记忆系统能力和治理路线。
- `memory-system-new-window-handoff.md`：新维护窗口快速上下文。
- `project-study-sop.md`：项目学习路径。
- `windows-compatibility.md`：Windows 兼容性记录。

## 文档检查

```powershell
rg -n "<旧品牌或旧路径关键字>" README.md docs
rg -n "<未完成或过期阶段措辞>" README.md docs
git diff --check
```

如果命令有命中，必须判断是合法历史事实还是过期表达；当前用户文档中不应出现旧品牌、旧路径或未完成措辞。
