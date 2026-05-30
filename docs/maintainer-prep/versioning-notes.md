# 版本管理记录

## 当前基线

- 当前目标分支：`main`
- v3 最终版功能提交：`feat: complete RepoHarness v3 parity closeout`
- v4 优化提交：`refactor: Phase 1 & Phase 2 start - code cleanup, security fix, Claude Code Skill compatibility`
- 文档同步提交建议：`docs: sync RepoHarness v4 documentation`
- 参考基线：参考仓库 v3 commit `91a7c17`，v4 commit `9fca8c5`

## 公开入口

- Python 包：`repo_harness`
- CLI：`repo-harness`
- 模块入口：`python -m repo_harness`
- 本地状态目录：`.repo-harness/`

旧品牌入口、旧状态目录和旧配置文件不再作为当前支持面维护。

## 提交分组

- 功能代码：`feat: ...`
- 修复：`fix: ...`
- 测试：`test: ...`
- 文档：`docs: ...`
- CI：`ci: ...`
- 重构：`refactor: ...`

文档同步必须使用独立 `docs:` 提交，避免和功能代码混在一起。

## 合并规则

- 功能分支进入 `main` 优先使用 `git merge --ff-only`。
- 如果不能 fast-forward，先停下来检查分支差异，不强行合并。
- 文档更新基于已合入 `main` 的功能状态。

## 验证规则

功能提交前：

```powershell
uv run pytest tests -q --basetemp C:\tmp\rh-test
uv run ruff check .
git diff --check
```

文档提交前：

```powershell
git diff --check
```

并检查 README/docs 中是否出现旧品牌、旧路径、未完成措辞或乱码。

## 记忆治理规则

任何版本都必须保留：

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

不得通过版本升级把候选事实直接写入 durable topics。
