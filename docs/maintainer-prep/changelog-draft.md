# 更新日志草案

## 文档说明

这份文档用于维护待发布变更的 release note 草案。它帮助维护者在开发过程中持续积累用户可读的变更说明，发版前再按实际版本号、提交范围和用户影响裁剪成正式 changelog。

本文不是完整历史 changelog。已经发布或已经形成存档基线的内容，应在正式发布记录、Git tag 或提交历史中保留可追溯来源。

## 更新规则

- 待发布内容放在 `## 待发布记录` 下。
- 每个批次按日期追加小节，标题格式为 `YYYY-MM-DD：变更主题`。
- 后续发版时，可以把对应日期小节整理成正式版本条目。
- 不同性质的变更不要混写：兼容性修复、文档补强、CI、品牌重命名应分开描述。

## 待发布记录

### 2026-05-09：开源文档本机参数清理

#### 已修复

- README 和新手指南中的 Windows 示例不再使用维护者本机绝对路径，改为通用占位符。
- 维护者文档中的个人归档仓库、开发分支和本机 file link 已改为占位符或仓库相对路径。
- Anthropic-compatible 示例不再写死具体服务商 endpoint 或专用 API Key 名称。
- 未跟踪的新窗口 handoff 文档不纳入提交；如未来提交，需要先单独清理本机路径和推送命令。

### 2026-05-07：Code-Aware File Summaries v1

#### 已新增

- `read_file` 读取完整 Python 文件后，`file_summaries` 会生成受限结构摘要，包含少量 imports、classes、functions 和 constants。
- Python 片段、解析失败和非 Python 文件继续使用原有前三行短摘要。
- README、getting-started 和 memory roadmap 同步说明该能力边界。

#### 行为边界

- 摘要长度上限、freshness 失效、memory section 预算和 Memory Pack 语义保持不变。
- 该能力不调用模型、不引入 embedding / database / background service，也不缓存函数体或 docstring 长文本。

### 2026-05-06：Explainable Retrieval v1

#### 已新增

- memory retrieval 现在会生成结构化 explanation，包含 `text`、`kind`、`source`、`tags`、`created_at`、`score` 和 `score_breakdown`。
- prompt metadata 的 `relevant_memory` 增加 `selected_explanations`，并保持 prompt 正文只渲染 note 文本。
- REPL 新增只读命令 `/memory_explain <query>`，用于查看 lexical retrieval 的 deterministic ranking 结果。
- README 和新手指南补充 `/memory_explain <query>` 入口说明。
- 维护者 roadmap 明确 Explainable Retrieval v1 的边界：默认 lexical retrieval，不引入向量库或外部索引。

#### 行为边界

- 该批次包含代码、测试和文档更新。
- 记忆系统原则保持确定性、轻量、文件可追踪；解释结果应能回溯到 `.repo-harness/memory/` 或 working context 来源。
- `/memory_explain` 不写 memory、不触发模型调用；`score_breakdown` 不进入 prompt 正文。

### 2026-05-06：Memory Pack v1 验证边界加固

#### 已修复

- `repo-harness memory validate` 现在会拒绝 durable topic 文件名与文件内 topic slug 不一致的 pack。
- `working_context` payload 现在必须是合法 `working-context-v1` JSON object。
- memory pack zip 中的重复 archive entry 会被拒绝。
- 导出 resume state 和 run artifacts 时会跳过 symlinked state files，避免意外打包仓库外文件。

#### 用户影响

- 导入前检查更可信，错误 pack 会更早失败。
- conservative merge 语义不变：导入仍不覆盖已有 memory、session 或 run 文件。

### 2026-05-05：Memory Pack v1

#### 已新增

- 新增 memory pack 本地导出、导入、检查和验证能力，支持 `safe-transfer`、`continue-work`、`full-recovery` 三个 preset。
- 新增 REPL 命令 `/memory_pack` 和 `/memory-pack`，为普通用户提供结果导向菜单。
- 新增 advanced CLI：`repo-harness memory export/import/inspect/validate`，用于脚本化和模块级控制。

#### 行为边界

- 默认 `safe-transfer` 只迁移 durable memory。
- 导入采用 conservative merge，不覆盖已有记忆、session 或 run 文件。
- `full-recovery` 明确提示可能包含 prompts、tool outputs、local paths、reports 和 traces。

#### 文档维护

- 更新 README、getting-started 和维护者文档。
- 将文档同步列为功能完成后的必需维护环节。

### 2026-05-03：Windows 适配与维护者文档补强

#### 已修复

- 新增 `tzdata` 运行时依赖，使 benchmark 的时区元数据在 Windows 以及其他未内置 IANA 时区数据的环境中稳定工作。
- 加固 benchmark verifier 的执行逻辑：当 verifier 使用 `python3 -c ...` 形式时，改为调用当前 Python 解释器。
- 稳定 benchmark 的可复现性 locale 输出，避免运行工件随宿主机 locale 静默漂移。
- 在过滤后的运行时环境中保留 Windows shell 启动所需的关键变量。
- 改进 `run_shell` 的可移植性：当命令语义依赖 POSIX shell 时，优先使用兼容 shell。
- README 增加 macOS / Linux、Windows PowerShell 和 Windows CMD 的分层启动与环境变量示例，降低不同系统命令混写造成的误用。
- 修正 `.gitignore` 对 `docs/` 的整体忽略，确保维护者文档、架构文档和 changelog 能进入版本管理。
- 新增最小 CircleCI 配置，用 lint 和测试保护 Python 基线。
- 补齐测试依赖的 review-pack 和 architecture 文档骨架。
- 新增 `docs/getting-started.md`，把首次配置、API Key、REPL 指令、Windows 使用注意事项和产品化 Q&A 从 README 中分离出来。

#### 维护者备注

- 这批变更应描述为跨平台兼容性修复、可复现性修复和维护者文档补强，而不是“本机配置特例修复”。
- 如果后续继续推进 `RepoHarness` 重命名，建议把重命名作为单独的破坏性变更条目，不要混入这条 Windows 适配记录。
