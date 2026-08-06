# G3 方案：多语言写入与英文 canonical 检索的合同闭合

> 依据：《RepoHarness 产品缺口交接》G3（已对当前 HEAD 复核确认仍存在）。
> 目标合同：Review Record 同时保留多语言 `source_text` 与英文 `canonical_text`；只有人工 accept/edit 后的英文 canonical 进 Durable Memory 和 ASCII 检索；`source_text` 仅作来源证据，不参与排序。不引入 Embedding。

## 一、现状（已复核）

- `TOKEN_PATTERN`（memory.py:34）纯 ASCII，`_tokenize`/`_canonical_note_text`（491-512）对中文分词结果为空集 → 中文 durable note 检索不到。
- Review Record（memory.py:329-339）只有 `text`/`original_text`/`topic`/`original_topic`；`original_text` 语义是"编辑前旧值"（非 source/canonical 分离）。
- `reject_durable_reason` 接受中文（memory_coordinator.py:30-33 支持中文行模式），中文正文原样入队。
- durable 写入：`accept_durable_review`（memory.py:1246-1263）用 `final_text` promote 到 durable_store；检索用 `_tokenize`（ASCII）。
- 测试 `test_memory_coordinator.py:84` 断言中文正文通过安全过滤。

## 二、目标合同（已确认）

```
多语言 source_text ──> Review Queue ──> 人工 accept/edit ──> 英文 canonical_text 进 Durable Memory
   │                                                          │
   └── 仅作来源证据(provenance)                                └── ASCII + Topic + Alias 检索
```

- 用户可中文或英文交互；候选入队时同时保存 `source_text`（原文）与 `canonical_text`（英文规范）。
- 人工 Review 的重点：检查英文 canonical 是否发生语义偏移。
- 只有 accept/edit 后的英文 canonical 进 Durable Memory 和排序。
- `source_text` 仅证据，不参与排序。
- 不引入 Embedding；不要求用户翻译，只要求判断语义一致。

## 三、设计

### 1. Review Record schema 扩展（review-queue.jsonl）

在现有 record 基础上增加字段：

```python
record = {
    "schema_version": DURABLE_REVIEW_QUEUE_SCHEMA,   # 不变
    "id": ..., "created_at": ..., "topic": ..., "source": ..., "status": "pending",
    "text": canonical_text,        # 语义变为"英文 canonical"(durable 写入用)
    "source_text": 原文,            # 新增：多语言原文证据
    "canonical_text": 英文规范,     # 新增：显式英文
    "original_text": 原文,          # 兼容保留(编辑前旧值语义,现等价 source_text)
    "provenance": {...run/session/task...},  # 新增或复用 source
}
```

**兼容**：老 record 无 `canonical_text`/`source_text` 时，读入时 `canonical_text = text`（即假设已 canonical），`source_text = original_text or text`。这样旧数据不崩、不阻塞。

### 2. 语言检测与 canonical 生成（不引入翻译模型）

- 新增 `_is_ascii(text)`：判断文本是否纯 ASCII。
- **非 ASCII 候选**：`canonical_text` 默认 = `text`（原文，未翻译），但**标记 `canonical_needs_review: true`**——进队列时即提示人工需确认英文规范。
- **ASCII 候选**：`canonical_text = text`，无需标记。
- **不做自动翻译**（不引入第二模型/Embedding）；`canonical_needs_review` 是"人工需检查语义偏移"的提示，不是翻译产物。

### 3. durable 写入只用英文 canonical（强制边界）

- `accept_durable_review`（memory.py:1246）：promote 用 `canonical_text`（而非 `text`/`original_text`）。
- **强制拦截（双 Agent 审核裁决，核心闭环）**：accept 时若 `canonical_needs_review=True` 且最终 `canonical_text` 仍非 ASCII（`_is_ascii` 为假），**拒绝 promote** 并返回明确提示"请先 edit 出英文 canonical 或 reject"——中文原文不得静默进 durable。
- **放行豁免（机器可判定）**：仅当 `_canonical_note_text(canonical_text)` 非空（即 ASCII 检索能命中，如含英文关键 token 的中英混合）才可放行。判断标准是"检索合同是否成立"，不是"用户是否愿意"。
- `enqueue_durable_reviews` 的去重（pending_keys/reviewed keys）用 `(topic, canonical_text)`，并同步 `reviewed_self_iteration_keys` 与 `has_note` 预过滤（避免 self-iteration 重复入队）。
- 检索 `_tokenize`/`_canonical_note_text` 只作用于 durable store 里的英文 canonical（现有机制不变，因为 durable 只存可检索英文）。

### 4. 展示与人工审核路径

- `/memory review` 的候选展示同时显示 `source_text` 与 `canonical_text`，标注 `canonical_needs_review` 提示。
- 人工 edit 时改 `canonical_text`（等价现状 edit `text`）。

## 四、最小改动范围

1. `memory.py`：
   - `DurableMemoryReviewQueue.enqueue`：record 增加 `source_text`/`canonical_text`/`canonical_needs_review`；去重键改用 canonical。
   - `_mark_locked`/`update_pending`：edit 时更新 canonical_text（保持 source_text 不变）。
   - `load`：老 record 兼容（缺字段默认）。
   - `accept_durable_review`（在 LayeredMemory）：promote 用 canonical_text。
   - 新增 `_is_ascii` 与 `_canonical_text_for`（非 ASCII 标记 needs_review）。
2. `core/memory_coordinator.py`：`extract_durable_promotions` 产出的 (topic, text) 增加 canonical 处理；`reject_durable_reason` 不变（仍接受中文）。
3. `cli.py` 的 `/memory review` 展示：显示 source/canonical + needs_review 提示。
4. `tests/test_memory_coordinator.py:84`：现有断言（中文通过过滤）应保持——中文仍可入队，但 canonical_needs_review 标记。

## 五、失败测试计划（先补测试再实现）

新增 `tests/test_memory_canonicalization.py`：

1. `test_chinese_candidate_keeps_source_and_marks_canonical_needs_review`：中文候选入队后 `source_text==原文`、`canonical_text` 存在、`canonical_needs_review is True`。
2. `test_ascii_candidate_canonical_equals_text`：英文候选 `canonical_text==text`、`canonical_needs_review is False`。
3. `test_accept_without_edit_blocks_non_ascii_canonical`（**核心主线**）：中文候选直接 accept（不 edit）**必须被拦截**，返回错误提示，durable 不得出现中文 note——此测试先失败于现状。
4. `test_accept_promotes_canonical_not_source`：人工先 edit 出英文 canonical 后 accept，durable 写入的是英文 canonical，不是中文 source。
5. `test_edit_canonical_keeps_source_text`：人工 edit canonical 后 source_text 不变。
6. `test_old_record_without_canonical_fields_migrates`：无 canonical/source 字段的旧 record 读入后 canonical=text；**旧中文 record 读入时补 `canonical_needs_review=True`**（迁移不能静默假设已 canonical）。
7. `test_durable_retrieval_only_sees_canonical`：英文 canonical 可检索；中文 source_text 不参与排序。
8. `test_mixed_ascii_retrievable_canonical_allowed`：中英混合且 ASCII 可命中的 canonical（如"提交信息用 English commit messages"）放行进 durable。

## 六、边界与红线

- **不引入 Embedding/向量库/翻译模型**（文档非目标）。
- **不要求用户翻译**：只要求人工 Review 判断 canonical 语义是否一致（canonical_needs_review 提示）。
- **不静默翻译后直接写入**：非 ASCII 候选 canonical 默认=原文+标记，人工确认后才进 durable。
- 兼容旧数据（缺字段默认）、不破坏现有测试语义（中文仍可入队，只是标记）。
- 不削弱反粉饰测试。
- Review Queue 治理不变：人工 accept 才进 durable。

## 七、待确认

1. `canonical_needs_review` 提示的实现位置（record 字段 vs 展示层派生）——已定：字段（可持久化、可查询）。
2. 中文候选的 canonical 边界——已定（双 Agent 审核裁决）：**非 ASCII canonical 进 durable 是强制拦截的**。accept 时若 canonical 仍非 ASCII 且无法检索命中（`_canonical_note_text` 为空），必须 edit 出英文 canonical 或 reject；放行豁免仅限"ASCII 检索可命中"的中英混合（机器可判定），不取决于用户是否愿意。
3. provenance 是否复用现有 `source` 字段（已含 origin/run/session/task）——已定：复用，不新增。
