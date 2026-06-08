# Windows 兼容性记录

## 文档说明

这份文档用于记录项目在 Windows 环境下的兼容性策略、验证方式、已知边界和每次相关调整。它服务当前维护者和未来维护者，帮助判断 Windows 问题是平台差异、依赖缺失、shell 语义不一致，还是项目代码需要收敛边界。

本文不是“Windows 专版设计文档”。项目目标仍然是在统一代码路径下支持 Windows、macOS 和 Linux。

## 更新规则

- 每次 Windows 相关适配新增一个日期小节。
- 如果 CLI 入口、包名、本地状态目录或验证命令变化，应在新记录中说明，不直接覆盖旧记录。
- 已知边界需要保留，除非后续记录明确说明该边界已经被移除。

## 兼容性记录

### 2026-06-03：v6 安全加固 Windows 适配

#### 变更

- `runtime.path()` 路径逃逸检查从 `os.path.commonpath()` 改为 `Path.is_relative_to()`，Windows 大小写不敏感场景更安全。
- `shell_env()` 新增 `_sanitize_path()` 过滤 PATH 中的临时目录（`AppData\Local\Temp` 等），防止 PATH 注入攻击。
- `SessionStore.save()` 改为原子写入（`tempfile + os.replace`），Windows 上避免写入中断导致文件损坏。
- `run_shell` 捕获 `subprocess.TimeoutExpired` 返回结构化错误（原为 raw traceback，Windows 上中文乱码）。
- sandbox 默认 `best_effort`，Windows 上 bubblewrap 不可用时回退并输出 stderr 警告。

#### 验证命令

```powershell
uv run pytest tests/test_sandbox_runner.py tests/test_sandbox_config.py tests/test_dangerous_commands.py -q
uv run pytest tests/test_repo_harness.py -q -k "run_shell"
```

### 2026-05-19：最终版 shell 与 sandbox 合同

#### 当前策略

- Windows 用户可以从 CMD 或 PowerShell 启动 `repo-harness`。
- `run_shell` 优先使用可用的 POSIX-compatible shell，以稳定执行模型常见命令；不可用时回退平台默认 shell。
- shell 环境使用 allowlist，保留 Windows 启动所需变量，同时避免把无关敏感变量带入工具执行。
- Sandbox `required` 在后端不可用时 fail closed；Windows fallback 会写入明确 metadata。

#### 验证命令

```powershell
uv run pytest tests/test_sandbox_runner.py tests/test_sandbox_config.py tests/test_tool_policy_acceptance.py -q
uv run pytest tests/test_repo_harness.py -q -k "run_shell"
```

### 2026-05-03：Windows CMD / PowerShell 适配基线

#### 适配原则

- 保持 `RepoHarness.ask()` 主循环、工具白名单、approval 模型、memory、checkpoint、trace、report、prompt cache 和 benchmark 口径不变。
- 只在操作系统接触面做兼容：shell 环境、shell 执行、benchmark verifier、时区依赖和用户文档。
- CMD / PowerShell 是 Windows 用户的启动入口；Git Bash 只是内部 shell 工具的可选兼容路径。

#### 已处理的问题

- Windows 默认不一定有 IANA timezone 数据，因此运行时依赖显式声明 `tzdata`。
- Windows 默认不一定有 `python3` 命令，因此 benchmark verifier 中的 `python3 -c ...` 改由当前 `sys.executable` 执行。
- 过滤后的 shell 环境需要保留 `ComSpec`、`SystemRoot`、`PATHEXT`、`USERPROFILE`、`APPDATA` 和 `LOCALAPPDATA`，否则 Windows shell 或用户级工具可能无法启动。
- agent 常生成 POSIX 风格命令；当机器上存在 Git Bash 或 `sh` 时，`run_shell` 优先使用兼容 shell。没有兼容 shell 时回退平台默认 shell。
- `docs/` 需要纳入版本管理，不能被 `.gitignore` 整体忽略；本地私有文档放入 `docs/local/`。

#### 验证命令

Windows CMD：

```bat
cmd /c uv run python -m repo_harness --help
```

Windows PowerShell：

```powershell
powershell -NoProfile -Command "uv run python -m repo_harness --help"
```

通用回归：

```bash
uv run pytest tests/test_repo_harness.py tests/test_evaluator.py -q
uv run ruff check .
uv run pytest -q
```

#### 已知边界

- Git Bash 不是 Windows 必装项。没有 Git Bash 时，平台 shell 仍会被使用，但模型生成的 POSIX 风格命令可能需要用户或模型改写。
- CircleCI 第一版只保护 Linux/Python 基线；Windows 入口通过本地 CMD / PowerShell 验证和单元测试覆盖。
- 本轮不改变 `uv.lock` 的忽略策略。
- 当前 Windows 入口以 `repo-harness` 和 `python -m repo_harness` 为准。
