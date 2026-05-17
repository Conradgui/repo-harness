# RepoHarness Memory System 新窗口交接文档

## v3 Compat Phase 2 Workflow And UX

Phase 2 is complete when skills, todo ledger, bounded workers, sandbox runner, runtime control plane seams, optional Textual TUI, and release evidence scenario gate are implemented, tested, documented, committed, and pushed on `repo-harness/v3-compat-phase2`.

Memory governance is unchanged:

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

Skills and workers may help produce controlled prompt text or runtime artifacts, but they must not bypass Review Queue promotion or directly write durable topics.

## v3 Compat Phase 1 Foundation

The current foundation release adds `.repo-harness.toml`, provider profiles for OpenAI / Anthropic / DeepSeek, DeepSeek through the Anthropic-compatible protocol, tool policy, and `/remember <text>`.

Memory governance is unchanged:

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

`/remember` and memory self-iteration only queue Review Queue candidates. Phase 2 owns skills, todo ledger, worker manager, sandbox, runtime control plane layering, Textual TUI, and release evidence. Reference v3 commit: `91a7c17`; old stable reference tag: `archive-before-repoharness-rename-20260503`.

## 目的

这份文档用于在新 Codex 窗口中无缝继续 RepoHarness 记忆系统迭代。新窗口应优先读取本文，再读取：

- `docs/maintainer-prep/memory-system-iteration-roadmap.md`
- `docs/maintainer-prep/patch-summary.md`
- `docs/maintainer-prep/changelog-draft.md`
- `README.md`
- `docs/getting-started.md`

记忆系统后续迭代必须继续保持核心产品原则：**确定性、轻量、文件可追踪、分层清晰**。

## 使用前刷新 Git 状态

本文是记忆系统方向交接，不再硬编码本机路径、远端仓库或分支状态。新窗口开始前先运行：

```powershell
git status --short
git rev-parse --abbrev-ref HEAD
git rev-parse --short HEAD
```

重要策略：

- 以当前工作区实际分支和用户指令为准。
- 未确认合并策略前，不要推送到主分支。
- 每个较大阶段完成后必须包含：代码实现、测试、文档同步、代码审查、修复审查意见、重新验证、commit、push。

## 已完成阶段

### 1. RepoHarness 品牌基线

RepoHarness 当前公开入口：

- distribution name：`repo-harness`
- import package：`repo_harness`
- console script：`repo-harness`
- module entry：`python -m repo_harness`
- 本地状态目录：`.repo-harness/`

旧品牌入口和旧状态迁移兼容已经移除；后续不要重新引入旧 prompt、旧 CLI 或旧状态目录说明。

`AGENT.md` / `AGENTS.md` 不新增。文档已说明它们是可选约定；仓库没有该文件不是 bug。

### 2. Memory Pack v1

Memory Pack v1 已实现：

- 新增 `repo_harness/memory_pack.py`
- 本地 zip pack，标准库实现，不引入数据库、向量索引、后台服务或外部依赖
- manifest：`repo-harness-memory-pack.json`
- payload：`payload/`
- modules：
  - `durable_knowledge`
  - `working_context`
  - `resume_state`
  - `run_artifacts`
- presets：
  - `safe-transfer`
  - `continue-work`
  - `full-recovery`
- REPL：
  - `/memory_pack`
  - `/memory-pack`
- advanced CLI：
  - `repo-harness memory export`
  - `repo-harness memory import`
  - `repo-harness memory inspect`
  - `repo-harness memory validate`

导入策略：

- 默认 conservative merge
- 不覆盖已有 memory、session、run 文件
- durable memory 做 note 级合并
- working context 导入为 snapshot，不覆盖当前 session memory
- sessions/runs 冲突时跳过并写 import report
- 拒绝 zip 路径穿越、重复 archive entry、不支持 schema、payload 不一致

已做过的加固：

- durable topic 文件名必须与文件内 topic slug 一致
- `working_context` payload 必须是合法 `working-context-v1`
- duplicate zip entry 拒绝
- 导出 sessions/runs 时跳过 symlink 或解析后不在源目录内的文件

### 3. Explainable Retrieval v1

Explainable Retrieval v1 已实现。

核心能力：

- memory retrieval 暴露结构化 explanation
- 每条 explanation 包含：
  - `text`
  - `kind`
  - `source`
  - `tags`
  - `created_at`
  - `score`
  - `score_breakdown`
- `score_breakdown` 当前包含：
  - `tag_match`
  - `keyword_overlap`
  - `recency`
  - `kind`
- `ContextManager` metadata 增加：
  - `metadata["relevant_memory"]["selected_explanations"]`
- prompt 正文保持简洁：
  - `Relevant memory:` 只渲染 note 文本
  - 不把 `score`、`score_breakdown`、debug metadata 塞进 prompt
- REPL 新增：
  - `/memory_explain <query>`
- `/help` 已展示 `/memory_explain <query>`

重要审查修复：

- durable retrieval 恢复 topic title 匹配能力。实现通过私有 `_search_text` 参与检索，公开 explanation 不暴露内部字段。
- `ContextManager` 现在优先从同一次 `retrieval_explanations()` 结果派生 selected notes，避免 selected notes 与 selected explanations 双路径错位。
- 文档已修正为当前真实 schema，不再把 `durable source` 写成 `score_breakdown` 字段。

### 4. Code-Aware File Summaries v1

Code-Aware File Summaries v1 已完成：

- Python：完整读取 `.py` 文件时，使用标准库 AST 提取少量 imports、classes、functions 和 uppercase constants。
- Markdown：完整读取 `.md` / `.markdown` 文件时，提取 ATX headings，并忽略 fenced code block 内标题。
- Config：完整读取 `.json` / `.toml` / `.ini` / `.cfg` / `.yaml` / `.yml` 文件时，只提取浅层 keys / sections。
- Tests：Python 测试文件优先提取 `test_*` functions、`Test*` classes 和 class 内 `test_*` methods。
- 片段读取、解析失败或没有可提取结构时继续回退到前三行摘要。
- 摘要继续受长度上限、固定项数上限、freshness hash 和 memory budget 约束。

### 5. Fuzzy Lexical Retrieval v1

当前只实现非常克制的 lexical normalization：

- `memory-pack`
- `memory_pack`
- `MemoryPack`
- `memory pack`

这些写法可以互相召回。

实现边界：

- 只做大小写、分隔符和 camelCase / PascalCase 归一化。
- 不做 edit distance。
- 不做同义词表。
- 不做 semantic retrieval。
- 不引入 embedding、向量库、后台索引或外部服务。
- durable promotion subject key 使用独立 canonicalizer，不使用检索专用 joined token，避免长期事实去重被污染。

### 6. Durable Topic Taxonomy Decision

当前产品决定：**不做 Topic Configuration**。

长期 durable topic 继续固定为四类：

- `project-conventions`
- `key-decisions`
- `dependency-facts`
- `user-preferences`

不要新增：

- `.repo-harness/memory/config.json`
- `.repo-harness/memory/topics.yml`
- 自定义 topic taxonomy

原因：长期记忆系统应尽最大可能保持简洁；如果需要中间层，优先做 Review Queue，而不是开放长期 topic 结构。

## 最近验证结果

最近已运行：

```text
pytest tests -q
144 passed
```

```text
ruff check .
All checks passed!
```

```text
git diff --check
无 whitespace error；Windows 环境下可能只出现 CRLF 提示。
```

如果 Windows 环境下 pytest temp 目录出现 ACL 问题，使用仓库外临时目录作为 `--basetemp`，不要把临时目录纳入提交。

## 当前记忆系统结构

RepoHarness 当前记忆系统仍是确定性、轻量、文件可追踪的分层系统，不是向量数据库，也不是完整聊天历史压缩器。

主要层次：

1. **Session history**
   - 完整对话和工具调用历史，保存在 session。
   - 由 `ContextManager` 按预算拼进 prompt。

2. **Working memory**
   - 当前任务轻量状态。
   - 包含 `task_summary`、`recent_files`。

3. **File summaries**
   - 对读过的文件保存摘要。
   - 带 freshness hash，文件修改后摘要失效。

4. **Episodic notes**
   - 会话内事件型记忆。
   - 默认有数量上限。

5. **Durable memory**
   - 跨会话持久记忆。
   - 落盘在：

```text
.repo-harness/memory/MEMORY.md
.repo-harness/memory/topics/*.md
```

默认 topic：

- `project-conventions`
- `key-decisions`
- `dependency-facts`
- `user-preferences`

## 后续路线

当前 roadmap 已把“可迁移、可审核、可解释”三块收尾为稳定 v1 基线：

1. Memory Portability v1
   - `safe-transfer` 只导出 accepted durable memory。
   - `continue-work` 导出 durable memory 和 working context，导入后只保存 working context snapshot。
   - `full-recovery` 导出 durable memory、working context、sessions/checkpoints 和 run artifacts，并保留 privacy warning。
2. Memory Governance v1
   - durable candidates 先进入 `.repo-harness/memory/review-queue.jsonl`。
   - `/memory review` 的 accept/edit 才写入 durable topics。
   - `report.json` 中 `durable_review_queued` 表示入队候选，`durable_promotions` 只表示真正写入 durable topics 的内容。
3. Explainable Retrieval v1
   - `/memory_explain <query>` 只读，不调用模型，不写 session。
   - explanation 包含 `score`、`score_breakdown`、`kind`、`source`、`tags`、`created_at`。
   - `selected_explanations` 只记录实际进入 prompt 的 memory 解释。

明确不做：

- Topic Configuration。
- Semantic Retrieval adapter。
- edit distance / synonym table / embedding / vector DB。

Code-Aware File Summaries v1 和 Fuzzy Lexical Retrieval v1 也已完成，并作为上述三块能力的支撑能力保留。

**Memory Self-Iteration v1 已完成 v1 基线**。它提供透明、可控、可审核的轻量自迭代，不新增语义检索复杂度。

原因：

- Code-Aware summaries 已支持 Python / Markdown / config / Python test files，继续保持 freshness hash、固定上限和 fallback。
- Durable memory 候选已先进入 `.repo-harness/memory/review-queue.jsonl`，通过 `/memory review` 的 accept/edit 才会写入 durable topics。
- Pending queue 不进入 prompt memory、不参与 `/memory_explain`，也不进入 `safe-transfer` memory pack。
- Memory Pack v1 已覆盖 `safe-transfer`、`continue-work` 和 `full-recovery` 三种迁移/恢复场景。
- `/memory_explain` 已能解释 lexical 和 fuzzy lexical 命中，不需要引入 embedding 或 vector DB。
- `/memory self_iteration` 只读展示最近一次 self-iteration 状态，不触发 compaction、不生成候选、不写 durable topics。
- 后续工作不再继续扩展 Self-Iteration v1；优先单独评估 Memory Safety And Redaction，或处理 README 截图重制/删除、release/branch 收尾。

建议边界：

- 不调用模型生成摘要。
- 不引入重依赖。
- 摘要仍必须绑定 freshness hash。
- 文件被写入后继续失效旧摘要。
- 所有 durable memory 候选继续先进入 Review Queue，不允许绕过审核直接写入 durable topics。
- Review Queue edit 后也必须继续执行 secret-shaped / transient / noisy 过滤。
- Memory Self-Iteration v1 产生的可复用事实仍只能进入 Review Queue，不能直接写 durable topics。
- `report.json` 应记录 `episodic_compactions`、`self_iteration_review_queued` 和 `self_iteration_rejections`，方便复盘自整理行为。

## 新窗口执行规则

新窗口继续任务时，请遵守：

- 遇到功能实现，优先使用 subagent：
  - Explorer：只读审查当前路径、测试结构、风险点。
  - Worker A/B/C：按文件边界拆分实现、CLI/REPL、测试文档。
  - 主 agent：集成、冲突处理、验证、审查、提交、推送。
- 除非涉及关键产品判断，否则自动持续推进。
- 关键判断必须停下确认：
  - 是否改变默认导出范围
  - 是否允许覆盖已有 memory/session/run
  - 是否引入新依赖、数据库、向量检索或外部服务
  - 是否弱化 full-recovery 隐私提示
  - 是否修改 durable memory markdown 格式兼容性
  - 是否重新引入 Topic Configuration 或 Semantic Retrieval
- 每次阶段完成前必须做代码审查。
- 审查发现的重要问题必须修复并重新跑相关测试。
- 文档同步是完成门禁，不是可选项。

## 推送策略

推送前必须重新确认目标 remote 和目标分支。不要把本机路径、个人 remote、临时目录或一次性推送命令写进可提交文档。

## 已知环境注意事项

- `.git` 目录可能触发 dubious ownership，按当前环境选择合适的 `safe.directory` 设置，不要把本机绝对路径提交进文档。
- pytest 临时目录可能触发 Windows ACL 问题，建议使用仓库外 `--basetemp`。
- `ruff check .` 曾出现 3 条 `拒绝访问` warning，但退出码为 0 且输出 `All checks passed!`。
- 仓库中可能有权限受限的 pytest 临时目录 warning，不应纳入提交。

## 新窗口建议开场指令

可以在新窗口中发送：

```text
请先读取 docs/maintainer-prep/memory-system-new-window-handoff.md 和 docs/maintainer-prep/memory-system-iteration-roadmap.md，然后继续推进 RepoHarness 记忆系统下一阶段。保持“确定性、轻量、文件可追踪、分层清晰”，质量优先，必要时启用 subagent，阶段完成后必须做代码审查、测试和文档同步；提交或推送前先确认当前目标分支。
```
