# 安全策略

repo-harness 是一个运行在本地仓库里的 coding agent runtime，它设计为**有权限执行 shell 命令、读写文件、管理长期记忆**。因此安全问题需要严肃对待。

## 支持的版本

本项目尚未对外发布正式 release，处于 `0.x` 开发期。当前只维护最新提交；安全修复会优先合入默认分支，并记录在 changelog 中。

## 报告漏洞

请**不要**在公开 issue 中披露疑似漏洞。请通过 GitHub 私有渠道上报：

- 打开 [Security Advisories](https://github.com/Conradgui/repo-harness/security/advisories/new)（需仓库权限）
- 或在对应仓库的 Issues 中新建 `[SECURITY]` 前缀的 issue 并明确标注不要公开讨论

请包含：

- 受影响版本 / 提交
- 复现步骤（尽量最小）
- 影响评估（能否越界执行、读取敏感信息、绕过 sandbox 等）
- 如果可能，附带补丁建议

## 处理承诺

- 我们会尽快确认并评估（目标 72 小时内回复）。
- 修复合入前，不会公开漏洞细节。
- 修复后会记录到 changelog，并视严重度补发安全说明。

## 已知边界（诚实声明）

本项目对 sandbox 的定位是**分层防御，不是完全隔离**。请在使用前理解以下边界：

- `read_only` 模式下**不执行任何 shell 命令**，且 `excluded_commands` 在该模式下不提供豁免（ADR-007）。这是当前最可靠的防线。
- 命令字符串过滤（`excluded_commands` 等）**不是安全边界**——历史上有通过 shell 元字符绕过过滤的真实案例（见 ADR-007）。它只是可用性便利，不能替代 `read_only` / `required` 沙箱。
- `best_effort` 模式不承诺隔离。
- provider 配置中只保存环境变量名，不保存 key 值；但请确保 API key 环境变量的访问权限受操作系统保护。
- 脱敏（secret sanitizer）基于值匹配，依赖 secret 真实值出现在环境中；拼接构造的 secret 可能漏脱敏。涉及敏感环境的部署请额外审计 trace 与报告产物。

## 威胁模型概览

- **信任边界**：本地用户 ↔ agent runtime ↔ 模型 provider。模型输出被视为不可信输入，任何工具调用都必须经过 permission gate、tool policy 与 sandbox。
- **fail-closed 原则**：配置错误、后端不可用、模式不识别时以失败告终，不静默回退到更宽松的执行（ADR-002 / ADR-007）。
- **权限单点**：所有工具调用经 `PermissionChecker.check()` 决策，工具实现不自行判断能否执行；这使得"什么情况下 agent 能写文件"只需读一个函数。

## 审计与痕迹

每次运行产出 `task_state.json` / `trace.jsonl` / `report.json` 等工件，权限决策与安全事件进入 session event bus，可用于事后审计。
