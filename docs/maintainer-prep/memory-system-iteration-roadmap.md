# RepoHarness Memory System Iteration Roadmap

本文记录 RepoHarness 记忆系统的阶段性设计判断、已完成 v1 基线和后续迭代方向。它用于在后续开发窗口中区分已收尾能力和真正的下一阶段工作。

## Current Baseline

RepoHarness 当前的记忆系统是一个确定性、轻量、文件可追踪的分层系统，而不是向量数据库或完整聊天历史压缩器。

现有记忆层包括：

- `session history`：完整对话和工具调用历史，保存在 session 中。
- `working memory`：当前任务摘要和最近接触文件。
- `file summaries`：读过文件的短摘要，带 freshness hash。
- `episodic notes`：会话内事件型笔记，当前有数量上限。
- `durable memory`：跨会话长期记忆，保存到 `.repo-harness/memory/` 下的 markdown 文件。
- `checkpoint`：恢复执行现场的状态，不完全属于 memory，但与恢复能力强相关。

当前 durable memory 默认 topic：

- `project-conventions`
- `key-decisions`
- `dependency-facts`
- `user-preferences`

## Product Direction

记忆系统后续分两条线推进：

1. **Memory portability**
   用户换电脑或迁移环境时，可以选择性导出、打包、导入记忆系统，不需要从零配置。

2. **Memory intelligence**
   RepoHarness 在使用过程中逐步沉淀稳定事实、偏好、项目约定和代码理解，并在后续任务中更准确、可解释地复用。

当前阶段已经完成 **Memory Portability / Governance / Explainability v1** 收尾：Memory Pack 负责可迁移，Review Queue 负责可审核，`/memory_explain` 负责可解释。下一阶段才进入简单、可审核的 **Memory Self-Iteration v1**。

## Memory Pack v1 Decisions

### Default Experience

第一版默认采用 **Safe transfer**：

- 只导出长期知识记忆。
- 不默认导出 session、trace、run artifact、完整对话或 shell 输出。
- 导入时采用保守合并，不覆盖已有内容。

原因：

- 隐私风险最低。
- 最符合用户对“迁移记忆”的直觉。
- 路径和机器环境兼容性最好。
- 与历史 `.pico/` 到 `.repo-harness/` 的迁移原则一致：复制缺失内容，不覆盖已有内容。

### Presets

Memory pack 使用结果导向的 preset：

- `safe-transfer`
  - 导出 durable knowledge。
  - 适合把长期记忆带到另一台电脑。

- `continue-work`
  - 导出 durable knowledge 和 working context。
  - 适合同一个仓库在另一台电脑继续当前工作。

- `full-recovery`
  - 导出 durable knowledge、working context、resume state 和 run artifacts。
  - 适合完整恢复或审计。
  - 必须提示可能包含 prompts、tool outputs、本地路径、reports 和 traces。

### Internal Modules

内部模块建议为：

- `durable_knowledge`
  - `.repo-harness/memory/MEMORY.md`
  - `.repo-harness/memory/topics/*.md`

- `working_context`
  - 当前 task summary
  - recent files
  - file summaries
  - episodic notes

- `resume_state`
  - sessions
  - checkpoints

- `run_artifacts`
  - reports
  - traces
  - run outputs

### Entrypoints

REPL 入口面向普通用户：

```text
/memory_pack
/memory-pack
```

`/help` 中展示主入口：

```text
/memory_pack  Export, import, inspect, or validate memory packs.
```

`/memory_pack` 菜单按最终效果展示，而不是按内部模块展示：

```text
Memory pack

1. Move my stable memory to another computer
   Export project conventions, decisions, dependency facts, and user preferences.

2. Continue this repo's current work on another computer
   Export stable memory plus current task context and recent file summaries.

3. Create a full recovery archive
   Export stable memory, working context, sessions, checkpoints, and run artifacts.
   May include prompts, tool outputs, local paths, reports, and traces.

4. Import a memory pack
   Merge a memory pack into this workspace without overwriting existing memory.

5. Inspect or validate a memory pack
   Preview what is inside a pack before importing it.

0. Cancel

Advanced module control:
  Use `repo-harness memory export` or `repo-harness memory import <pack>`.
```

CLI 入口面向高级用户和脚本化：

```text
repo-harness memory export --preset safe-transfer
repo-harness memory export --preset continue-work
repo-harness memory export --preset full-recovery
repo-harness memory export --modules durable_knowledge,working_context
repo-harness memory export --custom
repo-harness memory import <pack>
repo-harness memory inspect <pack>
repo-harness memory validate <pack>
```

### Package Format

导出包建议使用 `.zip`：

```text
repo-harness-memory-pack-YYYYMMDD-HHMMSS.zip
```

包内结构：

```text
repo-harness-memory-pack.json
payload/
```

manifest 示例：

```json
{
  "schema_version": "memory-pack-v1",
  "created_at": "2026-05-05T00:00:00Z",
  "repo_harness_version": "0.1.0",
  "preset": "safe-transfer",
  "modules": ["durable_knowledge"],
  "source": {
    "workspace_fingerprint": "...",
    "cwd_hint": "..."
  },
  "counts": {
    "durable_topics": 4,
    "session_files": 0,
    "run_files": 0
  },
  "warnings": []
}
```

### Import Policy

默认导入策略是 **conservative merge**：

- 不覆盖已有文件。
- durable memory 做 note 级合并。
- 重复 note 跳过。
- 同 topic 新 note 追加。
- session、run 文件如果已存在则跳过。
- 导入结果写入 import report。

导入报告建议保存到：

```text
.repo-harness/memory/imports/import-YYYYMMDD-HHMMSS.json
```

`working_context` 第一版不直接覆盖当前 session memory。建议先导入为独立 snapshot：

```text
.repo-harness/memory/imported-working-contexts/<pack_id>.json
```

后续可以增加 advanced apply 操作。

### Validation And Governance

Memory Pack v1 的 validate 边界必须和导入边界一致。一个 pack 只有在 payload 结构可解释、路径安全、模块声明一致时，才允许 inspect 或 import。

当前治理规则：

- zip entry 不能重复，不能包含绝对路径、反斜杠、空 path、`.`、`..` 或 Windows drive colon。
- manifest 中的 payload 列表必须和 zip 实际 payload 文件完全一致。
- 每个 payload 文件必须匹配 manifest 中记录的 size 和 sha256。
- durable topic 文件名必须和文件内 `- topic:` slug 一致。
- `working_context` 必须是 UTF-8 JSON object，`schema_version` 必须为 `working-context-v1`，`memory` 必须是 object。
- export sessions/runs 时跳过 symlinked state files，避免把仓库外文件打入 pack。

这些规则服务于同一个原则：记忆系统继续保持确定性、轻量、文件可追踪，而不是依赖隐式信任或不可解释的二进制状态。

## Completed Memory Intelligence v1 Baseline

以下内容记录已经完成或明确收窄的 v1 基线，避免后续窗口把这些能力继续当作待办。

### 1. Explainable Retrieval v1（已完成）

目标：让用户和维护者知道某条 memory 为什么被召回，同时保持当前记忆系统确定性、轻量、文件可追踪。

第一版边界：

- 增加 REPL 命令 `/memory_explain <query>`，用于解释查询对应的 memory selection。
- 继续使用默认 lexical retrieval，不引入向量库、embedding index 或后台服务。
- 对每条候选 memory 生成结构化 `score_breakdown`，至少区分 tag match、keyword overlap、recency 和 kind；source 作为独立可追踪字段保留。
- 对最终进入上下文的条目生成 `selected_explanations`，结构化记录 selected note、source、kind、tags、created_at、score 和 score_breakdown。
- 在 prompt metadata 或 run report 中保存 selected note、source、kind、score_breakdown 和 selected_explanations，便于复盘。
- durable memory 的 `source` 使用 topic slug，例如 `project-conventions`；维护者可据此追踪到 `.repo-harness/memory/topics/<topic>.md`。

不做内容：

- 不实现 semantic retrieval。
- 不把解释交给模型自由生成。
- 不写入或自动提升 durable memory。
- 不改变 Memory Pack v1 的导入、导出、验证语义。

收益：

- 提升调试能力。
- 降低“模型为什么突然引用这条记忆”的黑箱感。
- 为当前 lexical retrieval 提供可复盘、可测试的调试基线。

当前输出字段：

```json
{
  "query": "pytest windows shell",
  "selected_explanations": [
    {
      "text": "Prefer Windows PowerShell examples when documenting Windows commands.",
      "kind": "durable",
      "source": "project-conventions",
      "tags": ["convention"],
      "created_at": "2026-05-06T10:00:00+00:00",
      "score": 2000.0,
      "score_breakdown": {
        "tag_match": 0,
        "keyword_overlap": 2,
        "recency": 1778061600.0,
        "kind": 0
      }
    }
  ]
}
```

### 2. Code-Aware File Summaries（已完成）

当前 `summarize_read_result()` 主要截取文件前几行，对代码理解较弱。

当前 v1 状态：

- 已实现 Python AST 结构摘要，只在确认 `read_file` 读取完整 `.py` 文件时启用。
- 已实现 Markdown heading 摘要，忽略 fenced code block 内标题。
- 已实现 JSON / TOML / INI / CFG / YAML 浅层 config 摘要。
- 已实现 Python test file 摘要，优先提取 `test_*` functions、`Test*` classes 和 class 内 `test_*` methods。
- 摘要继续受 `summarize_read_result(limit=180)` 控制，不提高 memory 预算。
- 只提取少量结构名称；超出上限用 `(+N)` 表示。
- 片段读取、解析失败或没有可提取结构时继续回退到前三行短摘要。
- freshness hash、`FILE_SUMMARY_LIMIT`、`WORKING_FILE_LIMIT`、`RELEVANT_MEMORY_LIMIT` 和 Memory Pack 语义均未改变。

已完成能力：

- 对 Python 文件提取 imports、classes、functions、top-level constants。
- 对 markdown 提取标题结构。
- 对 config 文件提取关键字段。
- 对测试文件提取 test names。
- 文件摘要继续带 freshness hash，避免过期复用。

收益：

- recent file summary 更有工程价值。
- 减少重复读文件。
- 提升跨轮代码任务连续性。

后续如继续扩展更多文件类型，必须保持固定上限、确定性解析和 freshness 失效语义。

### 3. Durable Topic Taxonomy Decision（已完成）

当前 durable topic 固定为四类：

- `project-conventions`
- `key-decisions`
- `dependency-facts`
- `user-preferences`

当前产品决定：**不实现 Topic Configuration**。

原因：

- 长期记忆系统应该尽最大可能保持简洁。
- 自定义 topic taxonomy 会增加导入、合并、去重、解释和迁移复杂度。
- 过多 topic 容易让 durable memory 变成半结构化文件堆，削弱“文件可追踪”和“可维护”的核心原则。
- 如果需要中间层，应使用 review queue 作为进入长期记忆前的缓冲，而不是开放长期 topic 结构。

明确不做：

- 不新增 `.repo-harness/memory/config.json`。
- 不新增 `.repo-harness/memory/topics.yml`。
- 不开放用户或 agent 自定义 durable topic。
- 不让 Memory Pack v1/v2 依赖可变 topic taxonomy。

### 4. Durable Memory Review Queue（已完成）

当前 durable promotion 已改为 review queue：最终回答中可解析、通过安全过滤的长期事实候选，不再直接写入 durable topics。

当前 v1 状态：

- Agent 发现疑似长期事实时，先写入 pending queue。
- 用户通过 `/memory review` 审核。
- 支持 accept、edit、reject、skip。
- accepted 后再进入 durable topics。
- edit 后会再次执行 secret-shaped / transient / noisy 过滤。
- `report.json` 中 `durable_promotions` 只表示真正写入 durable topics 的内容；自动候选入队记录在 `durable_review_queued`。
- Pending queue 不进入 prompt memory、不参与 `/memory_explain`、不进入 `safe-transfer` memory pack。

路径：

```text
.repo-harness/memory/review-queue.jsonl
```

收益：

- 避免错误事实自动进入长期记忆。
- 允许用户编辑长期记忆表述。
- 更符合“持续自我迭代但受用户控制”的产品方向。

### 5. Fuzzy Lexical Retrieval v1（已完成）

当前 lexical retrieval 继续保持默认检索方式，但允许做非常克制的词面归一化，让用户不必精确记住分隔符和大小写。

当前 v1 边界：

- 做 token normalization。
- 做 separator-aware matching。
- 支持 `memory-pack`、`memory_pack`、`MemoryPack`、`memory pack` 这类写法互相召回。
- 支持常见分隔符拆分：`_`、`-`、`.`、`/`、`\`。
- 支持 camelCase / PascalCase 拆分。
- 继续通过现有 `keyword_overlap` 解释命中原因。

明确不做：

- 不做 edit distance。
- 不做同义词表或 alias map。
- 不做字符 n-gram 相似度。
- 不调用模型判断词义相近。
- 不引入 embedding、向量库、后台索引或 semantic retrieval。

原则：

- exact lexical match 仍然自然优先。
- normalization 只扩大确定性 token 集合，不改变 durable memory 格式。
- `/memory_explain` 必须继续能解释召回原因。

收益：

- 用户不需要精确记住 `memory_pack` 还是 `memory-pack`。
- 保持实现轻量、确定性、可测试。
- 避免 semantic retrieval 带来的索引、迁移和调试复杂度。

## Later Work

后续只从简单、可审核的 Memory Self-Iteration v1 开始；Memory Safety And Redaction 之后单独评估。

### 1. Memory Self-Iteration v1

当前 episodic notes 超过上限后直接截断。下一阶段可以做简单、确定性的自迭代归档。

可做能力：

- 将旧 episodic notes 汇总成 session summary。
- 将可复用事实候选送入 review queue。
- 将纯过程噪声丢弃。

收益：

- 长任务上下文更稳定。
- 减少有用事件被截断丢失。

### 2. Memory Safety And Redaction

后续需要强化记忆导出和 durable promotion 的安全边界。

可做能力：

- 导出前扫描 secret-shaped 内容。
- full recovery export 必须二次确认。
- manifest 记录 redaction summary。
- validate 检查危险路径和 schema mismatch。
- import 时拒绝 `../` 路径穿越。

收益：

- 降低跨设备和跨团队迁移时的信息泄露风险。
- 让 memory pack 可以更放心地分享或备份。

## Recommended Implementation Order

当前阶段已经把“可迁移、可审核、可解释”三块收尾为稳定 v1 基线：

1. Memory Portability v1（已完成）
   - `safe-transfer` 只导出 accepted durable memory。
   - `continue-work` 导出 durable memory 和 working context，导入后保存 working context snapshot，不覆盖当前 session。
   - `full-recovery` 导出 durable memory、working context、sessions/checkpoints 和 run artifacts，并保留隐私 warning。
   - import 继续 conservative merge，不覆盖已有 memory/session/run 文件。
   - inspect/validate 继续严格检查 schema、路径穿越、重复 entry、topic slug mismatch 和 working context payload。

2. Memory Governance v1（已完成）
   - durable candidates 先进入 `.repo-harness/memory/review-queue.jsonl`。
   - `/memory review` 的 accept/edit 才写入 durable topics，reject 不写入，skip 保持 pending。
   - edit/accept 继续执行 secret-shaped、transient、noisy 过滤。
   - `report.json` 中 `durable_review_queued` 表示本轮入队候选，`durable_promotions` 只表示真正写入 durable topics 的内容，`durable_rejections` 表示被安全过滤拒绝的候选。

3. Explainable Retrieval v1（已完成）
   - `/memory_explain <query>` 只读，不调用模型，不写 session。
   - explanation 包含 `score`、`score_breakdown`、`kind`、`source`、`tags`、`created_at`。
   - `prompt_metadata.relevant_memory.selected_explanations` 记录实际进入 prompt 的 memory 解释。
   - prompt 正文只渲染 `Relevant memory:` note 文本，不暴露 debug score。
   - fuzzy lexical normalization 只做大小写、分隔符、camelCase/PascalCase 归一化，不做 edit distance、同义词、semantic retrieval、embedding 或 vector DB。

下一阶段只进入 **Memory Self-Iteration v1**，目标是简单、可审核的自迭代：

- 将长任务中的有用 session 片段整理为 bounded episodic summaries。
- 将可复用事实作为 durable candidates 送入 Review Queue，仍不允许绕过审核直接写 durable topics。
- 保持 lexical retrieval 为默认和 fallback，不引入语义检索复杂度。

之后再单独评估 Memory Safety And Redaction：

- export 前 secret-shaped scan。
- redaction summary。
- import/export safety hardening。

## Handoff Prompt For Next Window

可以在新窗口中发送本文，并使用下面这段提示继续推进：

```text
请基于 docs/maintainer-prep/memory-system-iteration-roadmap.md，
继续推进 RepoHarness 记忆系统下一阶段：
- 已完成 Memory Portability v1、Memory Governance v1、Explainable Retrieval v1、Fuzzy Lexical Retrieval v1、Code-Aware Summaries v1 和 Durable Memory Review Queue v1
- 不做 Topic Configuration、Semantic Retrieval、edit distance、同义词表、embedding 或 vector DB
- 下一步只推进 Memory Self-Iteration v1，保持简单、可审核、确定性优先
- 任何可复用事实进入 durable memory 前必须继续经过 Review Queue
- 阶段完成后运行完整测试，并更新 README / getting-started / maintainer-prep 文档
```

