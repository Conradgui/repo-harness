# 修复摘要

## 根因与代码位置

### 1. 缺少时区数据依赖声明

- 文件：[pyproject.toml](/C:/Users/Administrator/Desktop/cc/P1test/pyproject.toml:10)
- 现象：benchmark 和 evaluator 相关测试在真正执行前就失败，因为 `ZoneInfo("Asia/Shanghai")` 在 Windows 上无法解析。
- 问题：项目实际依赖 IANA 时区数据，但没有声明 `tzdata` 依赖。
- 更正方式：把 `tzdata` 加入运行时依赖。
- 更正原因：这样可以把时区能力要求显式化，避免依赖宿主机是否自带时区数据。

### 2. 可复现性元数据依赖宿主机 locale

- 文件：[pico/evaluator.py](/C:/Users/Administrator/Desktop/cc/P1test/pico/evaluator.py:121)
- 现象：benchmark 产物中的元数据会随着宿主机 locale 改变。
- 问题：所谓“可复现性”输出引用了机器当前 locale，而不是稳定约定值。
- 更正方式：为 benchmark 的可复现性元数据输出稳定 locale 值。
- 更正原因：同一份 benchmark 在不同电脑上应尽量产出可比较、可复核的结果。

### 3. benchmark verifier 默认假设存在 `python3`

- 文件：[pico/evaluator.py](/C:/Users/Administrator/Desktop/cc/P1test/pico/evaluator.py:129)、[pico/evaluator.py](/C:/Users/Administrator/Desktop/cc/P1test/pico/evaluator.py:505)
- 现象：即使任务本身已正确完成，Windows 上 verifier 仍会失败。
- 问题：verifier 以 shell 字符串方式执行，并默认存在 `python3` 命令。
- 更正方式：识别 `python3 -c ...` 形式的 verifier，并改用 `sys.executable` 执行。
- 更正原因：当前解释器路径比依赖命令名更可靠，也更适合托管测试环境。

### 4. shell 安全过滤误删 Windows 启动所需变量

- 文件：[pico/runtime.py](/C:/Users/Administrator/Desktop/cc/P1test/pico/runtime.py:512)
- 现象：shell 执行时报错，提示缺少 `%ComSpec%` 或 `%SystemRoot%`。
- 问题：过滤后的执行环境没有保留 Windows shell 启动所必需的基础变量。
- 更正方式：在过滤环境中保留 `ComSpec`、`SystemRoot` 和 `PATHEXT`。
- 更正原因：安全收敛应减少敏感暴露，但不能破坏 shell 的最小可运行条件。

### 5. runtime 没有保证与命令语法兼容的 shell

- 文件：[pico/tools.py](/C:/Users/Administrator/Desktop/cc/P1test/pico/tools.py:65)、[pico/tools.py](/C:/Users/Administrator/Desktop/cc/P1test/pico/tools.py:220)
- 现象：使用 POSIX 引号和 `printf` 的命令在 Windows 默认 shell 下执行失败。
- 问题：测试和命令内容默认使用 POSIX shell 语义，但 runtime 实际交给平台默认 shell 处理。
- 更正方式：优先选择 POSIX 兼容 shell，并为常见 Git Bash 路径提供显式兜底。
- 更正原因：这能让执行语义与测试和命令本身隐含的 contract 保持一致。

### 6. 测试依赖的文档骨架缺失

- 文件：
  - [docs/review-pack/README.md](/C:/Users/Administrator/Desktop/cc/P1test/docs/review-pack/README.md:1)
  - [docs/architecture/agent-harness-v1-overview.md](/C:/Users/Administrator/Desktop/cc/P1test/docs/architecture/agent-harness-v1-overview.md:1)
- 现象：测试套件因为找不到要求存在的文档而失败。
- 问题：仓库中缺少测试显式依赖的文档资产。
- 更正方式：补齐测试要求的文档骨架和基础内容。
- 更正原因：测试不应依赖缺失的受版本管理文件。

## 给维护者的建议备注

建议把本地机器描述为“复现环境”，而不是“问题根因”。真正的根因是一组偏向类 Unix 假设、对宿主机状态有依赖的代码和工程约束。
