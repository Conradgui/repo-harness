# RepoHarness Memory System Iteration Roadmap

本文记录 RepoHarness 记忆系统的阶段性设计判断和后续迭代方向。它用于在后续开发窗口中继续推进 memory pack、记忆治理和记忆智能能力。

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

第一阶段优先做 **Memory Portability and Governance v1**。记忆智能增强放到后续阶段逐步推进。

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

## Future Memory Intelligence Improvements

以下内容不放入第一阶段实现，后续逐项推进。

### 1. Explainable Retrieval

目标：让用户和维护者知道某条 memory 为什么被召回。

可做能力：

- 在 prompt metadata 中记录每条 selected memory 的命中原因。
- 区分 tag match、keyword overlap、recency、durable source。
- 增加 `/memory explain <query>` 或 advanced inspect 输出。
- 在 run report 中保存 selected note、source、kind、score breakdown。

收益：

- 提升调试能力。
- 降低“模型为什么突然引用这条记忆”的黑箱感。
- 为后续 semantic retrieval 提供可对比基线。

### 2. Code-Aware File Summaries

当前 `summarize_read_result()` 主要截取文件前几行，对代码理解较弱。

可做能力：

- 对 Python 文件提取 imports、classes、functions、top-level constants。
- 对 markdown 提取标题结构。
- 对 config 文件提取关键字段。
- 对测试文件提取 test names。
- 文件摘要继续带 freshness hash，避免过期复用。

收益：

- recent file summary 更有工程价值。
- 减少重复读文件。
- 提升跨轮代码任务连续性。

第一版可以只做标准库 AST 的 Python code summary，不引入复杂 parser。

### 3. Topic Configuration

当前 durable topic 固定为四类。后续可以允许项目配置 topic taxonomy。

可做能力：

```text
.repo-harness/memory/config.json
```

或：

```text
.repo-harness/memory/topics.yml
```

示例 topic：

- `architecture-decisions`
- `testing-strategy`
- `release-process`
- `security-boundaries`
- `team-preferences`

收益：

- 适配不同项目类型。
- 减少把所有事实塞进默认四类。
- 让 memory pack 更像可迁移知识库。

注意：

- 配置必须有 schema version。
- 默认四类仍应保留，避免新用户必须配置。

### 4. Durable Memory Review Queue

当前 durable promotion 依赖最终回答中出现可解析的长期事实。后续可以改成 review queue。

可做能力：

- Agent 发现疑似长期事实时，先写入 pending queue。
- 用户通过 `/memory review` 审核。
- 支持 accept、edit、reject。
- accepted 后再进入 durable topics。

建议路径：

```text
.repo-harness/memory/review-queue.jsonl
```

收益：

- 避免错误事实自动进入长期记忆。
- 允许用户编辑长期记忆表述。
- 更符合“持续自我迭代但受用户控制”的产品方向。

### 5. Episodic Compaction

当前 episodic notes 超过上限后直接截断。后续可以做压缩归档。

可做能力：

- 将旧 episodic notes 汇总成 session summary。
- 将可复用事实候选送入 review queue。
- 将纯过程噪声丢弃。

收益：

- 长任务上下文更稳定。
- 减少有用事件被截断丢失。

### 6. Optional Semantic Retrieval Adapter

不建议第一阶段上向量库。后续如果要做，应该是可选 adapter，而不是替换当前 lexical retrieval。

原则：

- lexical retrieval 保持默认和 fallback。
- semantic retrieval 必须可关闭。
- 索引文件必须可迁移或可重建。
- 不把 embeddings 当作唯一事实来源。

收益：

- 改善同义表达召回。
- 支持更自然的用户查询。

风险：

- 引入模型和索引复杂度。
- 跨设备迁移会涉及 embedding 兼容性。
- 调试成本明显升高。

### 7. Memory Safety And Redaction

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

建议后续分阶段推进：

1. Memory Pack v1
   - `memory_pack.py`
   - zip manifest
   - safe-transfer export/import
   - inspect/validate
   - `/memory_pack`
   - CLI advanced commands
   - tests and docs

2. Continue Work Support
   - working context export
   - imported working snapshots
   - no-overwrite import report

3. Full Recovery Archive
   - sessions/runs export
   - explicit risk prompt
   - conflict skip report

4. Explainable Retrieval
   - score breakdown
   - metadata/report exposure
   - memory explain command

5. Code-Aware Summaries
   - Python AST summaries first
   - markdown/config/test summaries later

6. Topic Configuration
   - memory topic schema
   - custom topic loading
   - docs and migration tests

7. Review Queue
   - pending durable facts
   - accept/edit/reject flow
   - `/memory review`

8. Optional Semantic Retrieval
   - adapter interface
   - lexical fallback
   - rebuildable local index

## Handoff Prompt For Next Window

可以在新窗口中发送本文，并使用下面这段提示继续推进：

```text
请基于 docs/maintainer-prep/memory-system-iteration-roadmap.md，
先实现 Memory Pack v1：
- 默认 safe-transfer
- 支持 /memory_pack 和 /memory-pack
- 支持 repo-harness memory export/import/inspect/validate
- 导入默认 conservative merge，不覆盖已有内容
- 先不要实现后续的 explainable retrieval、code-aware summaries、topic config、review queue 或 semantic retrieval
- 实现后运行完整测试，并更新 README / getting-started 文档
```

