# Windows 兼容性说明

这份说明记录本轮 Windows 适配的边界、根因和验证方式。它的目标是帮助维护者评审变更，而不是把 `pico` 拆成 Windows 版和类 Unix 版。

版本管理口径：本文件描述的是当前 Windows 适配阶段的兼容策略。后续如果执行 `RepoHarness` 重命名、改变 CLI 入口或改变本地状态目录，需要新增变更说明并同步更新验证命令。

## 适配原则

- 保持 `Pico.ask()` 主循环、工具白名单、approval 模型、memory、checkpoint、trace、report、prompt cache 和 benchmark 口径不变。
- 只在操作系统接触面做兼容：shell 环境、shell 执行、benchmark verifier、时区依赖和用户文档。
- CMD / PowerShell 是 Windows 用户的启动入口；Git Bash 只是内部 shell 工具的可选兼容路径。

## 已处理的问题

- Windows 默认不一定有 IANA timezone 数据，因此运行时依赖显式声明 `tzdata`。
- Windows 默认不一定有 `python3` 命令，因此 benchmark verifier 中的 `python3 -c ...` 改由当前 `sys.executable` 执行。
- 过滤后的 shell 环境需要保留 `ComSpec`、`SystemRoot`、`PATHEXT`、`USERPROFILE`、`APPDATA` 和 `LOCALAPPDATA`，否则 Windows shell 或用户级工具可能无法启动。
- agent 常生成 POSIX 风格命令；当机器上存在 Git Bash 或 `sh` 时，`run_shell` 优先使用兼容 shell。没有兼容 shell 时回退平台默认 shell。
- `docs/` 需要纳入版本管理，不能被 `.gitignore` 整体忽略；本地私有文档放入 `docs/local/`。

## 验证命令

Windows CMD：

```bat
cmd /c uv run python -m pico --help
```

Windows PowerShell：

```powershell
powershell -NoProfile -Command "uv run python -m pico --help"
```

通用回归：

```bash
uv run pytest tests/test_pico.py tests/test_evaluator.py -q
uv run ruff check .
uv run pytest -q
```

## 已知边界

- Git Bash 不是 Windows 必装项。没有 Git Bash 时，平台 shell 仍会被使用，但模型生成的 POSIX 风格命令可能需要用户或模型改写。
- CircleCI 第一版只保护 Linux/Python 基线；Windows 入口通过本地 CMD / PowerShell 验证和单元测试覆盖。
- 本轮不改变 `uv.lock` 的忽略策略。

## 变更记录

- `2026-05-03`：记录 Windows CMD / PowerShell 适配边界、验证命令和已知限制；该记录属于 `RepoHarness` 重命名前的兼容性基线。
