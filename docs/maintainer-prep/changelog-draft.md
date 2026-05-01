# 更新日志草案

## 未发布

### 已修复

- 新增 `tzdata` 运行时依赖，使 benchmark 的时区元数据在 Windows 以及其他未内置 IANA 时区数据的环境中可以稳定工作。
- 加固 benchmark verifier 的执行逻辑，在 verifier 使用 `python3 -c ...` 形式时改为调用当前 Python 解释器。
- 稳定 benchmark 的可复现性 locale 输出，避免产物随宿主机 locale 漂移。
- 在过滤后的运行时环境中保留 Windows shell 启动所需的关键变量。
- 改进 `run_shell` 的可移植性，在命令语法明显依赖 POSIX 语义时优先使用兼容 shell。
- README 增加 macOS / Linux、Windows PowerShell 和 Windows CMD 的分层启动与环境变量示例，避免不同系统命令混写。
- 修正 `.gitignore` 对 `docs/` 的整体忽略，确保维护者文档、架构文档和 changelog 可以进入版本管理。
- 新增最小 CircleCI 配置，用 lint 和测试保护 Python 基线。
- 补齐测试依赖的 review-pack 和 architecture 文档骨架。

### 给维护者的说明

- 这些变更应描述为跨平台兼容性修复和可复现性修复，而不是“本机配置特例修复”。
