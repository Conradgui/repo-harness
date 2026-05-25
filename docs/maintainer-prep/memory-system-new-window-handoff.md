# RepoHarness 记忆系统新窗口交接

## 快速结论

RepoHarness 的记忆系统当前以“可迁移、可审核、可解释”为核心。最终版 v3 能力完善和 Auto Issue Fix 真实执行与 dry-run 预演都没有降低记忆治理强度；skills、workers、evidence、Auto Issue Fix 和 memory organize 只能产生 Review Queue candidates 或外部证据，不能直接写 durable topics。

长期记忆路径固定为：

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

## 当前能力

- Memory Pack：`safe-transfer`、`continue-work`、`full-recovery`。
- Review Queue：候选事实先进入 `.repo-harness/memory/review-queue.jsonl`，schema 为 `durable-review-queue-v1`。
- `/memory review`：唯一 durable topics promotion 入口。
- `/memory_explain <query>`：只读解释检索结果。
- Explainable Retrieval 字段包括 `score_breakdown` 和 `selected_explanations`。
- Fuzzy Lexical Retrieval：克制的词面归一化。
- Memory Self-Iteration v1：可以整理 episodic notes，并把可复用事实送入 Review Queue candidates。
- `/memory self_iteration`：只读查看 `episodic_compactions`、`self_iteration_review_queued` 和 `self_iteration_rejections`，不会触发 compaction，也不会自动写 durable topics。

## 与 v3 能力完善的关系

最终版新增或补齐：

- `/memory organize` 只写 Review Queue candidates。
- Skills 不直接写 durable memory。
- Workers 不直接写 durable memory。
- Evidence / release scenario 不直接写 durable memory。
- Auto Issue Fix / auto review 只生成证据和审查记录，不直接写 durable memory。
- Reports 记录 `durable_review_queued`、self-iteration 结果和 runtime evidence，便于复盘。
- Code-Aware File Summaries v1 已完成；后续维护不要把它重新列为未完成能力。
- 当前不做 Topic Configuration；Semantic Retrieval、embedding 和 vector DB 不作为默认路线。
- Pending queue 不进入 prompt memory、`/memory_explain` 或 `safe-transfer`。

## 新窗口启动检查

```powershell
git status --short
git branch --show-current
git log --oneline --decorate -5
```

先读：

- `README.md`
- `docs/getting-started.md`
- `docs/maintainer-prep/repo-harness-v3-compat-status.md`
- `docs/maintainer-prep/memory-system-iteration-roadmap.md`
- `docs/maintainer-prep/patch-summary.md`

## 禁止事项

- 不让候选事实绕过 Review Queue。
- 不把 Review Queue 中的待审内容放进 prompt memory。
- 不让待审内容进入 `safe-transfer` memory pack。
- 不引入无审计的后台 durable memory 写入。
- 不因外部兼容诉求而降低 RepoHarness 的记忆治理。
