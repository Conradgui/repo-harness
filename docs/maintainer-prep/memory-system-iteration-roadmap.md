# RepoHarness 记忆系统路线

## 当前定位

RepoHarness 记忆系统已经完成 v1 收尾，并在最终版 v3 能力完善中保持自身优势：

- 可迁移：Memory Pack。
- 可审核：Review Queue。
- 可解释：Explainable Retrieval。
- 克制检索：Fuzzy Lexical Retrieval。

## 已完成能力

- Durable topics 四类文件治理。
- `.repo-harness/memory/review-queue.jsonl` 候选队列，schema 为 `durable-review-queue-v1`。
- `/remember <text>` 只入队候选。
- `/memory review` 支持 accept/edit/reject/skip；accept/edit 后才写 durable topics。
- `/memory_explain <query>` 只读解释 retrieval。
- Explainable Retrieval 记录 `score_breakdown` 和 `selected_explanations`。
- Memory Pack export/import/inspect/validate。
- `safe-transfer` 不导出待审候选。
- Memory Self-Iteration v1 只产生 bounded summary 和 Review Queue candidates。
- `/memory self_iteration` 只读展示自整理结果，不会触发 compaction，也不会自动写 durable topics。
- `/memory organize` 只整理候选，不直接写 durable topics。

## 当前治理合同

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

这个合同优先级高于参考仓库中的自动记忆写入方式。

## 与 runtime/workflow 的集成

- Skills 可以影响 prompt 和工具权限，但不能写 durable topics。
- Workers 可以产生 artifacts 和 parent report 汇总，但不能绕过 Review Queue。
- Evidence 可以记录 scenario 结果，但不能写 durable topics。
- Auto Issue Fix 可以生成证据包、自动审查门和 fallback 工件，但不能直接写 durable topics。
- Runtime report 应记录 queued、promoted、rejected 等可审计字段。
- 关键字段包括 `durable_review_queued`、`episodic_compactions`、`self_iteration_review_queued` 和 `self_iteration_rejections`。

## 当前边界

- Pending queue 不进入 prompt memory、`/memory_explain` 或 `safe-transfer`。
- 不做 Topic Configuration。
- Semantic Retrieval、embedding 和 vector DB 不作为当前默认路线。

## 后续维护方向

- 优先加强安全过滤、导入前审计和 report 可解释性。
- 如引入新检索策略，必须保持文件可追踪和解释链路。
- 如支持并发 review，需要补文件锁或乐观并发校验。
- 不默认引入向量库、后台服务或不可审计自动写入。
