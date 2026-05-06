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
