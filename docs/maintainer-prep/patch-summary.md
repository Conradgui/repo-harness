# 修复摘要

这份摘要用于维护者复盘本轮 Windows 适配和工程化补强。它既是当前维护者的工作记录，也给未来维护者提供代码定位、修复原因和验证依据。这里记录的是“为什么这样改”，不是完整 diff。

## 根因与代码位置

### 1. 缺少时区数据依赖声明

- 文件：[pyproject.toml](/C:/Users/Administrator/Desktop/cc/P1test/pyproject.toml:10)
- 现象：benchmark 和 evaluator 相关测试在真正执行前失败，因为 `ZoneInfo("Asia/Shanghai")` 在 Windows 上无法解析。
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
- 问题：测试和部分模型生成命令默认使用 POSIX shell 语义，但 runtime 实际交给平台默认 shell 处理。
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

### 7. 首次使用文档不够集中

- 文件：
  - [README.md](/C:/Users/Administrator/Desktop/cc/P1test/README.md:7)
  - [docs/getting-started.md](/C:/Users/Administrator/Desktop/cc/P1test/docs/getting-started.md:1)
- 现象：README 里已有安装和启动命令，但第一次使用者仍容易混淆项目根目录、PowerShell / CMD 环境变量、API Key 和 REPL 指令的边界。
- 问题：README 作为快速入口不适合承载完整新手教育；信息继续堆在 README 中会降低可读性。
- 更正方式：新增 `docs/getting-started.md`，并在 README 顶部和快速开始处加入入口链接。
- 更正原因：README 保持简洁，新手指南承接完整配置、使用技巧和产品化说明，维护成本更低。

## 维护者备注

- 建议把本地机器描述为“复现环境”，而不是“问题根因”。真正的根因是一组偏向类 Unix 假设、对宿主机状态有依赖的代码和工程约束。
- 这份摘要可以作为后续 review、release note、简历项目复盘的事实来源，但具体措辞需要按场景裁剪。
- 如果后续执行 `RepoHarness` 全量重命名，路径和类名会变化；这份摘要记录的是重命名前的修复位置。
