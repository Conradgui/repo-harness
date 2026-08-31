# ADR-009 · 自主场景的外部 clone 默认受限沙箱

**状态**：已执行
**日期**：2026-08-31
**性质**：行为变更 + Harness Engineering 修复

---

## 处境

审计发现（clone-sandbox-default-off）：Auto Issue Fix 的 live runner 用 `approval_policy="auto"` 在克隆仓库上构建 agent，沙箱配置来自 `sandbox_config_for_directory(clone_dir)`——clone 没有 `.repo-harness.toml` 时返回默认 `SandboxConfig()`（mode `off`）。两者叠加意味着：对任意来源的仓库，模型生成的每条命令既无沙箱也无审批，直接以用户主目录权限执行且具备网络访问能力。bubblewrap 后端的 argv 也没有网络隔离参数，即便配置了沙箱，出网仍然可能。

现有对抗测试（`test_sandbox_runner_gates.py`）反而锁定了 clone 默认 off 是预期行为——测试质量高，锁定的是不安全的默认值。

## 问题的性质

sandbox 是 invariant 还是 opt-in 决定其真实防御力。自主 harness 的最小默认应当 fail-safe：最需要防护的场景（未知来源仓库）恰好是默认不设防的场景。把安全完全留给调用方自觉，等于把边界交给概率。

## 决策

**Auto Issue Fix 对未显式声明沙箱 mode 的外部 clone 默认使用受限沙箱（`UNDECLARED_CLONE_SANDBOX`：mode `required` + backend `bubblewrap`）；bubblewrap 沙箱默认断网。**

具体语义：

- **显式声明才算声明**：`[sandbox]` 段里写了 `mode` 才是声明；显式 `mode = "off"` 依旧被尊重（[ADR-002](002-安全边界用开关而非删除实现.md) 精神：关掉边界改配置）。只写 `workspace_write` 之类的残缺声明不是 mode 声明，受限默认仍然生效。
- **fail closed**：`required` 模式在后端不可用时拒绝执行命令（`sandbox_unavailable` 事件 + 受控错误），而不是回退裸执行；`excluded_commands` 豁免在该模式下不生效（[ADR-007](007-read-only-不再有豁免.md) 的同一逻辑）。
- **网络隔离是沙箱的最小默认**：bubblewrap argv 默认带 `--unshare-net`；`allow_network = true`（toml `[sandbox]` 段或 `SandboxConfig(allow_network=True)`）是唯一的显式出网开关。

## 代价

- 没有 bubblewrap 的环境（macOS、部分 CI）上，AIF 修复 turn 的 `run_shell` 默认被拒。这是有意的 fail-safe：模型仍可读写文件、解释验证方式，只是不能在宿主机上执行任意命令。
- 既有显式 bubblewrap 配置升级后默认断网——需要出网的仓库必须在配置里声明 `allow_network = true`。
- 锁定旧默认（clone 默认 off）的既有测试已按 finding 的判断翻转断言。

## 为什么不是"保持默认 off、文档提醒配置沙箱"

提醒不改变边界：对未知来源仓库的默认不设防场景，正是自主执行最需要结构防护的场景。CLI 主路径不受影响（用户显式参数与全局配置优先级不变），变更只收自主场景的默认。

## 关联

- [ADR-002](002-安全边界用开关而非删除实现.md)：显式 mode = "off" 依旧被尊重
- [ADR-007](007-read-only-不再有豁免.md)：required 模式不吃命令过滤豁免
- [ADR-008](008-act-完成宣告需要验证证据.md)：同一审计的完成验证门
