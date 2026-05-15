# 修复摘要记录

## 文档说明

这份文档用于记录项目维护过程中的重要修复摘要。它帮助维护者复盘每次修复的背景、根因、涉及位置、处理方式和验证结果。

本文不是完整 diff，也不是最终 release note。每次阶段性修复应按日期追加记录，保留当时的路径、命令和判断口径，避免后续修改覆盖历史事实。

## 更新规则

- 每次修复批次新增一个日期小节，标题格式为 `YYYY-MM-DD：修复主题`。
- 旧记录中的路径、包名、命令和状态目录代表当时版本事实；后续重命名时不要直接改写旧记录。
- 如果新修复修正了旧判断，应新增“修正说明”，并明确说明旧判断为何不再适用。
- 每条记录尽量包含背景、修复内容、验证结果和后续注意。

## 修复记录

### 2026-05-15：旧品牌残留清理与维护者文档刷新

#### 背景

维护者文档中仍有旧品牌入口、旧状态目录迁移和旧截图引用相关描述，容易让后续维护窗口误判当前公开入口。本轮目标是让 RepoHarness 成为唯一当前品牌、入口和状态目录，并保留当前未提交的 Memory Self-Iteration v1 改动。

#### 修复内容

- 移除旧状态目录复制迁移逻辑，启动时只使用 `.repo-harness/`。
- 删除旧状态迁移测试，保留当前 `repo-harness` / `python -m repo_harness` 入口测试。
- README 移除旧截图引用；截图文件暂不删除，留待后续确认是否重制。
- 维护者 README、Windows 兼容性记录、版本记录、项目学习 SOP、架构概览、memory roadmap 和 handoff 同步当前 RepoHarness 事实。
- 新增文本守卫测试，防止 README、docs、源码、测试、配置和 ignore 规则重新引入旧品牌字面量。

#### 验证结果

- 旧品牌残留 targeted 文本检查：无输出。
- README/docs 旧截图引用检查：无输出。
- `uv run pytest tests/test_repo_harness.py -q -k "removed_brand or screenshots or module_execution or pyproject"`：5 passed。
- `uv run pytest tests/test_safety_invariants.py tests/test_repo_harness.py -q`：103 passed。
- `uv run pytest tests -q --basetemp C:\tmp\rh-test`：168 passed。
- `uv run ruff check .`：通过。
- `git diff --check`：无 whitespace error，仅有 Windows LF/CRLF 提示。

#### 后续注意

- 如果后续需要新的 README 截图，应使用当前 `repo-harness` CLI 和 `repo-harness>` REPL prompt 重新生成。
- 旧截图文件暂未删除，等待后续确认是否重制或移除；README 和 docs 不再引用它们。

### 2026-05-14：Memory Self-Iteration v1 透明可控推进

#### 背景

在“可迁移、可审核、可解释”三块收尾后，下一阶段进入简单记忆系统自迭代。用户明确要求 RepoHarness 对用户完全透明、完全可控，因此本轮不做黑盒自动长期记忆写入，而是把自整理行为暴露到 report 和只读 REPL 入口。

#### 修复内容

- run 收尾阶段新增 bounded episodic compaction，将过长 episodic notes 整理为 `episodic-compaction` 来源的短 note。
- self-iteration 发现的可复用长期事实候选只进入 `.repo-harness/memory/review-queue.jsonl`，source 标记为 `memory-self-iteration`，不直接写 durable topics。
- `report.json` 新增 `episodic_compactions`、`self_iteration_review_queued` 和 `self_iteration_rejections`，用于复盘自整理行为。
- REPL 新增只读入口 `/memory self_iteration`，展示最近一次 compaction、queued candidates、rejections 和 pending review 数量；该入口不触发 compaction、不生成候选、不写 memory。
- REPL 在最终回答后，如果 self-iteration 产生候选，会提示用户运行 `/memory review` 审核。
- README、getting-started、roadmap、handoff 和 changelog 同步透明可控边界。

#### 验证结果

- `uv run pytest tests/test_memory.py tests/test_memory_pack.py tests/test_repo_harness.py -q`：125 passed。
- `uv run pytest tests -q --basetemp C:\tmp\rh-test`：168 passed。
- `uv run ruff check .`：通过。
- `git diff --check`：无 whitespace error，仅有 Windows LF/CRLF 提示。

#### 后续注意

- Memory Self-Iteration v1 仍不调用模型生成摘要，不新增顶层 `repo-harness memory ...` CLI 子命令，不新增 semantic retrieval / embedding / vector DB。
- 长期记忆最终控制点继续只有 `/memory review`。

### 2026-05-14：Memory Portability / Governance / Explainability v1 收尾

#### 背景

记忆系统已经经历 Memory Pack、Explainable Retrieval、Fuzzy Lexical Retrieval、Code-Aware Summaries 和 Review Queue 多轮推进。本轮不新增大功能，也不进入 Memory Self-Iteration；目标是把“可迁移、可审核、可解释”三块收口为稳定、可测试、文档一致的 v1 基线。

#### 修复内容

- 文档统一确认 `safe-transfer`、`continue-work`、`full-recovery` 的边界：safe-transfer 只导出 accepted durable memory；continue-work 导入后只保存 working context snapshot；full-recovery 继续保留 privacy warning。
- 文档统一确认 Review Queue v1 边界：durable candidates 先进入 `.repo-harness/memory/review-queue.jsonl`，`/memory review` 的 accept/edit 后才写 durable topics，pending queue 不进入 prompt memory、`/memory_explain` 或 `safe-transfer`。
- 文档统一确认 report 字段语义：`durable_review_queued` 表示本轮入队候选，`durable_promotions` 只表示真正写入 durable topics 的内容，`durable_rejections` 表示被安全过滤拒绝的候选。
- 文档统一确认 Explainable Retrieval v1 边界：`/memory_explain` 只读，`selected_explanations` 记录实际进入 prompt 的 memory 解释，prompt 正文不暴露 debug score。
- roadmap 和 handoff 不再把已完成的 Code-Aware summaries、Review Queue 或三块 v1 收尾能力列为 future work；Memory Self-Iteration v1 已在后续批次完成 v1 基线。
- 追加文档一致性测试，保护 README、getting-started、roadmap、handoff、patch-summary 和 maintainer README 不再互相漂移。

#### 验证结果

- `uv run pytest tests -q --basetemp C:\tmp\rh-test`：160 passed。
- `uv run ruff check .`：通过。
- `git diff --check`：无 whitespace error，仅有 Windows LF/CRLF 提示。

#### 后续注意

- Memory Self-Iteration v1 后续批次已经完成 v1 基线；任何可复用事实仍必须进入 Review Queue。
- 继续不做 Topic Configuration、Semantic Retrieval、edit distance、同义词表、embedding 或 vector DB。
- Memory Safety And Redaction 后续单独评估，不和本轮收尾混在一起。

### 2026-05-12：Memory Intelligence v1 阶段推进

#### 背景

记忆系统后续路线确认继续保持固定 durable topic 四分类，不做 Topic Configuration、Semantic Retrieval、edit distance、同义词表、embedding 或 vector DB。本轮目标是补齐 Code-Aware File Summaries 剩余部分，并把 durable memory 自动写入改为用户审核队列。

#### 修复内容

- `summarize_read_result()` 继续保持 public API 不变，新增 Markdown heading、JSON / TOML / INI / CFG / YAML 浅层 config、Python test file 结构摘要。
- Markdown 摘要忽略 fenced code block 内标题，并覆盖 heading 末尾 `#`、不同 fence 长度和 closing fence trailing text 等边界。
- 文件摘要仍只在完整读取时启用，继续遵守 `limit=180`、固定项数上限、fallback、freshness hash 和 Memory Pack 语义。
- 新增 `.repo-harness/memory/review-queue.jsonl`，schema 为 `durable-review-queue-v1`。自动 durable candidates 先进入 pending queue，不再直接写 `.repo-harness/memory/topics/*.md`。
- REPL 新增 `/memory review`，支持 accept、edit、reject、skip。accept/edit 后才写入 durable topics；edit 后重新执行 secret-shaped / transient / noisy 过滤。
- `report.json` 中 `durable_promotions` 只表示真正写入 durable topics 的内容，自动入队候选记录在 `durable_review_queued`。
- Pending queue 不进入 prompt memory、不参与 `/memory_explain`，也不会被 `safe-transfer` memory pack 导出。
- benchmark durable-contract verifier 更新为检查 Review Queue 语义。
- README、getting-started、roadmap、handoff 同步当前实现和后续边界。

#### 验证结果

- `uv run pytest tests/test_memory.py tests/test_repo_harness.py tests/test_memory_pack.py tests/test_evaluator.py -q`：125 passed。
- `uv run pytest tests -q --basetemp <external-temp>`：159 passed。
- `uv run ruff check .`：通过。
- `git diff --check`：无 whitespace error，仅有 Windows CRLF 提示。

#### 后续注意

- Review Queue v1 按单 REPL / 单进程使用场景实现，未引入跨进程锁；如未来支持多进程并发审核，需要补充文件锁或乐观并发校验。
- 后续如果做 Episodic Compaction，任何可复用事实候选都必须进入 Review Queue，不应直接写 durable topics。
- 后续如果强化 Memory Safety，应优先覆盖 memory pack 导出前扫描和 full-recovery 二次确认。
- `memory-system-new-window-handoff.md` 已纳入维护者文档体系；后续更新 README、getting-started、memory roadmap、patch-summary 或记忆系统能力时，必须同步检查该 handoff 是否需要更新。

### 2026-05-11：Lexical Retrieval 归一化边界收窄

#### 背景

记忆系统后续路线确认不做 Topic Configuration，也不做 Semantic Retrieval。长期记忆 taxonomy 继续保持默认四类，避免 durable memory 结构膨胀；检索侧只补一个很克制的词面归一化能力，解决用户不记得 `memory-pack`、`memory_pack`、`MemoryPack` 等精确写法的问题。

#### 修复内容

- `memory.py` 的 tokenizer 增加大小写、常见分隔符和 camelCase / PascalCase 归一化。
- 支持 `_`、`-`、`.`、`/`、`\` 分隔符拆词，并额外保留 joined canonical token。
- tag token 也复用同一套归一化逻辑，保持 `/memory_explain` 的 `keyword_overlap` 可解释。
- durable promotion subject key 改用独立 canonicalizer，只使用拆分后的 normalized token，不使用检索专用 joined token，避免 `memory pack` / `memory-pack` / `MemoryPack` 长期事实无法互相 supersede。
- 明确不做 edit distance、同义词表、字符 n-gram、embedding、向量库或 semantic retrieval。
- README、getting-started 和 memory roadmap 同步说明边界；roadmap 删除 Topic Configuration / Optional Semantic Retrieval 作为后续推荐项，改为 fixed durable taxonomy、Review Queue 和 scoped lexical normalization。

#### 验证结果

- `pytest tests/test_memory.py tests/test_context_manager.py tests/test_repo_harness.py -q`：93 passed。
- `pytest tests -q`：144 passed。
- `ruff check .`：通过。
- `git diff --check`：无 whitespace error，仅有 Windows CRLF 提示。

#### 后续注意

- 后续如继续增强 retrieval，优先保持 `keyword_overlap` 可解释，不要新增不可复现的相似度来源。
- 如果要改善长期事实写入质量，优先做 Review Queue，而不是扩展 topic taxonomy。

### 2026-05-09：开源文档本机参数清理

#### 背景

开源文档中不应包含维护者本机绝对路径、个人归档仓库 URL 或开发现场分支名。README 和新手指南中的 Windows 示例曾使用真实本机目录，维护者记录中也有若干绝对 file link，这会降低文档可复用性并暴露不必要的本地环境信息。

#### 修复内容

- README 和 `docs/getting-started.md` 的 Windows 示例统一改为 `C:\path\to\repo-harness` / `C:\Users\YourName` 这类通用占位符。
- Anthropic-compatible 示例中的具体服务商地址和专用 API Key 名称改为通用 endpoint / key 表述，避免开源文档绑定某个开发环境或服务商。
- `docs/maintainer-prep/versioning-notes.md` 中的个人归档仓库、remote 和工作分支改为占位符，保留 tag 名称和提交哈希作为历史基线信息。
- `docs/maintainer-prep/patch-summary.md` 中的本机绝对 file link 改为仓库相对路径文本。
- 当时未跟踪的 `docs/maintainer-prep/memory-system-new-window-handoff.md` 保留在本地，未纳入该批次提交；该文件若后续提交，必须单独清理本机路径、临时目录和推送命令。

#### 验证结果

- 使用 `rg` 扫描 tracked 文档中的本机 Windows 用户目录、项目本地目录名、个人 GitHub 用户名、个人归档仓库名和开发现场分支名等参数。
- `uv run ruff check .`：通过。
- `git diff --check`：通过。

### 2026-05-07：Code-Aware File Summaries v1

#### 背景

RepoHarness 的 `file_summaries` 原本主要截取 `read_file` 输出的前几行。这符合 RepoHarness 轻量记忆原则，但对 Python 文件的信息密度较低，容易让 agent 为确认文件结构而重复读取。新能力必须保持短摘要、freshness 失效和确定性解析，不得把 memory 做成代码索引或知识库。

#### 修复内容

- `summarize_read_result()` 增加 Python AST 结构摘要，提取少量 imports、classes、functions 和 uppercase top-level constants。
- 只有 runtime 确认 `read_file` 从第 1 行覆盖完整 `.py` 文件时，才启用结构摘要；片段读取、解析失败和非 Python 文件继续回退到原有前三行摘要。
- 摘要继续受 `limit=180` 和 `set_file_summary()` 的既有裁剪/freshness 机制约束；未修改 memory section 预算、relevant memory 数量或 Memory Pack 语义。
- README、getting-started 和 memory roadmap 同步说明边界。

#### 验证结果

- `pytest tests/test_memory.py -q`：通过。
- `pytest tests/test_repo_harness.py -q`：通过。
- `pytest tests -q -p no:cacheprovider --basetemp <external-temp>`：通过。
- `ruff check .`：通过。

#### 后续注意

- 后续如扩展 Markdown/config/test summaries，必须继续保持固定摘要上限、确定性解析和 freshness 失效。
- 不应把函数体、docstring 长文本、完整 schema 或模型生成摘要写入 `file_summaries`。

### 2026-05-06：Explainable Retrieval v1

#### 背景

RepoHarness 记忆系统已经有 Memory Pack v1 和后续 intelligence roadmap，但已有 lexical retrieval 只能返回 note 文本，缺少可复盘的选择原因。维护者和用户需要在不引入向量库、不污染 prompt 的前提下，看清每条 relevant memory 为什么被选中。

#### 修复内容

- 在 memory retrieval 层新增结构化 explanation，包含 `score`、`score_breakdown`、`kind`、`source`、`tags` 和时间字段。
- `ContextManager` 在 `prompt_metadata.relevant_memory.selected_explanations` 中记录解释信息，同时 prompt 正文继续只渲染 note 文本。
- REPL 新增只读命令 `/memory_explain <query>`；空 query 返回用法提示，不调用模型、不写 session。
- README 增加 `/memory_explain <query>` 常用命令和 Explainable Retrieval v1 简介。
- `docs/getting-started.md` 增加排障示例，说明 `score_breakdown` 和 `selected_explanations` 的用途。
- `docs/maintainer-prep/memory-system-iteration-roadmap.md` 明确 v1 边界：只解释当前确定性 retrieval，不写 memory、不引入向量库、不改变 memory pack 语义。
- `docs/maintainer-prep/changelog-draft.md` 追加待发布文档记录。

#### 验证结果

- `pytest tests/test_memory.py tests/test_context_manager.py tests/test_repo_harness.py -q`：86 passed。
- `pytest tests -q`：136 passed。
- `ruff check .`：通过。
- `python -m repo_harness --help` 和 `repo-harness --help`：通过。

#### 后续注意

- `/memory_explain` 后续可以增强输出格式，但必须继续保持只读、不调用模型、不把 debug score 塞进 prompt。
- 如果未来增加 semantic retrieval，必须保持 lexical retrieval 作为默认和 fallback，并单独记录可关闭的 adapter 边界。

### 2026-05-06：Memory Pack v1 验证边界加固

#### 背景

对 `memory-pack-v1` 分支做代码审查时，发现 memory pack 的 validate/import 边界仍有几处治理风险：部分不一致或结构无效的包可以通过验证，导出时也可能跟随本地状态目录里的 symlink。

这些问题不改变 Memory Pack v1 的产品方向，但会削弱“validate 可信”和“文件可追踪”的基础假设，因此需要在进入下一阶段记忆系统迭代前修复。

#### 修复内容

- 拒绝 durable topic 文件名与文件内 `- topic:` slug 不一致的 pack，避免导入后 `MEMORY.md` 索引指向不存在的 topic 文件。
- 校验 `working_context` payload 必须是 UTF-8 JSON object，且 `schema_version` 必须为 `working-context-v1`，`memory` 必须是 object。
- 拒绝 zip 内重复 archive entry，避免同名 payload 被 `zipfile` 读取语义掩盖。
- 导出 sessions/runs 时跳过 symlink 或解析后不在源目录内的状态文件，避免把仓库外文件打入 memory pack。

#### 验证结果

- `pytest tests/test_memory_pack.py -q`：14 passed。

#### 后续注意

- 后续新增 memory pack 模块时，必须同步补 validate schema，不允许“manifest hash 通过但 payload 结构不可解释”。
- `inspect` 和 `validate` 应保持同一安全边界；能被 inspect 的 pack 也必须先满足 validate 规则。

### 2026-05-05：Memory Pack v1 与文档同步门禁

#### 背景

Memory Pack v1 新增了用户可见的记忆迁移能力：REPL 入口 `/memory_pack` / `/memory-pack`，以及 advanced CLI `repo-harness memory export/import/inspect/validate`。这类能力同时影响用户文档、维护者 SOP、本地持久化边界和后续 roadmap，不能只通过代码和测试完成。

#### 修复内容

- 新增 `repo_harness/memory_pack.py`，使用标准库 zip/json/pathlib 实现本地 memory pack，不引入数据库、向量索引、后台服务或外部依赖。
- 更新 `repo_harness/cli.py`，加入 `/memory_pack` 菜单和 `repo-harness memory ...` advanced 子命令。
- 更新 README 和 `docs/getting-started.md`，说明 presets、导入导出命令和 `full-recovery` 隐私风险。
- 新增 `docs/maintainer-prep/memory-system-iteration-roadmap.md`，记录 Memory Pack v1 与后续记忆系统迭代边界。
- 更新维护者文档规则，把“文档同步”列为功能完成后的必需门禁。

#### 验证结果

- `uv run pytest -q`：126 passed。
- `uv run ruff check .`：通过。
- `python -m repo_harness memory --help`：通过。
- `.venv\Scripts\repo-harness.exe memory --help`：通过。

#### 后续注意

- 后续涉及 public CLI、REPL、state、memory、checkpoint、runs、安全边界或持久化格式的改动，都必须同步复盘 README、getting-started、architecture、review-pack 和 maintainer-prep 文档。
- 如果判断某个文档不需要改，应在修复摘要或提交说明中写明理由，避免未来维护者误以为遗漏。

### 2026-05-03：Windows 适配与工程化补强

#### 背景

本次修复由 Windows 环境验证触发，暴露出项目在跨平台兼容性、benchmark 可复现性、shell 执行语义和维护者文档管理上的问题。

Windows 是复现环境，不是根因本身。真正需要修复的是代码库中隐含的类 Unix 假设、宿主机状态依赖和缺失的文档资产。

#### 修复内容

##### 1. 缺少时区数据依赖声明

- 文件：`pyproject.toml`
- 现象：benchmark 和 evaluator 相关测试在真正执行前失败，因为 `ZoneInfo("Asia/Shanghai")` 在 Windows 上无法解析。
- 问题：项目实际依赖 IANA 时区数据，但没有声明 `tzdata` 依赖。
- 更正方式：把 `tzdata` 加入运行时依赖。
- 更正原因：这样可以把时区能力要求显式化，避免依赖宿主机是否自带时区数据。

##### 2. 可复现性元数据依赖宿主机 locale

- 文件：`repo_harness/evaluator.py`
- 现象：benchmark 产物中的元数据会随着宿主机 locale 改变。
- 问题：所谓“可复现性”输出引用了机器当前 locale，而不是稳定约定值。
- 更正方式：为 benchmark 的可复现性元数据输出稳定 locale 值。
- 更正原因：同一份 benchmark 在不同电脑上应尽量产出可比较、可复核的结果。

##### 3. benchmark verifier 默认假设存在 `python3`

- 文件：`repo_harness/evaluator.py`
- 现象：即使任务本身已正确完成，Windows 上 verifier 仍会失败。
- 问题：verifier 以 shell 字符串方式执行，并默认存在 `python3` 命令。
- 更正方式：识别 `python3 -c ...` 形式的 verifier，并改用 `sys.executable` 执行。
- 更正原因：当前解释器路径比依赖命令名更可靠，也更适合托管测试环境。

##### 4. shell 安全过滤误删 Windows 启动所需变量

- 文件：`repo_harness/runtime.py`
- 现象：shell 执行时报错，提示缺少 `%ComSpec%` 或 `%SystemRoot%`。
- 问题：过滤后的执行环境没有保留 Windows shell 启动所必需的基础变量。
- 更正方式：在过滤环境中保留 `ComSpec`、`SystemRoot` 和 `PATHEXT`。
- 更正原因：安全收敛应减少敏感暴露，但不能破坏 shell 的最小可运行条件。

##### 5. runtime 没有保证与命令语法兼容的 shell

- 文件：`repo_harness/tools.py`
- 现象：使用 POSIX 引号和 `printf` 的命令在 Windows 默认 shell 下执行失败。
- 问题：测试和部分模型生成命令默认使用 POSIX shell 语义，但 runtime 实际交给平台默认 shell 处理。
- 更正方式：优先选择 POSIX 兼容 shell，并为常见 Git Bash 路径提供显式兜底。
- 更正原因：这能让执行语义与测试和命令本身隐含的 contract 保持一致。

##### 6. 测试依赖的文档骨架缺失

- 文件：
  - `docs/review-pack/README.md`
  - `docs/architecture/agent-harness-v1-overview.md`
- 现象：测试套件因为找不到要求存在的文档而失败。
- 问题：仓库中缺少测试显式依赖的文档资产。
- 更正方式：补齐测试要求的文档骨架和基础内容。
- 更正原因：测试不应依赖缺失的受版本管理文件。

##### 7. 首次使用文档不够集中

- 文件：
  - `README.md`
  - `docs/getting-started.md`
- 现象：README 里已有安装和启动命令，但第一次使用者仍容易混淆项目根目录、PowerShell / CMD 环境变量、API Key 和 REPL 指令的边界。
- 问题：README 作为快速入口不适合承载完整新手教育；信息继续堆在 README 中会降低可读性。
- 更正方式：新增 `docs/getting-started.md`，并在 README 顶部和快速开始处加入入口链接。
- 更正原因：README 保持简洁，新手指南承接完整配置、使用技巧和产品化说明，维护成本更低。

#### 验证结果

- `uv run pytest tests/test_repo_harness.py -q`：通过。
- `uv run ruff check .`：通过。
- `uv run pytest -q`：通过。
- Windows CMD / PowerShell 下 `uv run python -m repo_harness --help`：通过。

#### 后续注意

- 当前维护文档统一使用 RepoHarness 当前入口和 `.repo-harness/` 状态目录；旧品牌入口不再作为支持路径维护。
- 后续修复应继续追加新的日期记录，并在新记录中使用当时的当前包名、路径和命令。
