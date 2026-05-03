# 更新日志草案

这份草案用于维护者整理发布说明。它不是最终 release note，可以在发版前按实际版本号、提交范围和用户影响再做裁剪。写作口径以“项目自身的跨平台加固和工程化补强”为主，避免把问题归因成某一台机器的偶发现象。

## 未发布

### 已修复

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

### 维护者备注

- 这批变更应描述为跨平台兼容性修复、可复现性修复和维护者文档补强，而不是“本机配置特例修复”。
- 如果后续继续推进 `RepoHarness` 重命名，建议把当前 changelog 作为重命名前的稳定基线记录，不要混入品牌重命名的破坏性变更。
