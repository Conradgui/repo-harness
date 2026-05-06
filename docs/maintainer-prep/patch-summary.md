# 修复摘要记录

## 文档说明

这份文档用于记录项目维护过程中的重要修复摘要。它帮助维护者复盘每次修复的背景、根因、涉及位置、处理方式和验证结果。

本文不是完整 diff，也不是最终 release note。每次阶段性修复应按日期追加记录，保留当时的路径、命令和判断口径，避免后续修改覆盖历史事实。

## 更新规则

- 每次修复批次新增一个日期小节，标题格式为 `YYYY-MM-DD：修复主题`。
- 旧记录中的路径、包名、命令和状态目录代表当时版本事实；后续重命名时不要直接改写旧记录。
- 如果新修复修正了旧判断，应新增“修正说明”，并明确说明旧判断为何不再适用。
- 每条记录尽量包含背景、修复内容、验证结果和后续注意。

## 修复记录

### 2026-05-06：Memory Pack v1 验证边界加固

#### 背景

对 `memory-pack-v1` 分支做代码审查时，发现 memory pack 的 validate/import 边界仍有几处治理风险：部分不一致或结构无效的包可以通过验证，导出时也可能跟随本地状态目录里的 symlink。

这些问题不改变 Memory Pack v1 的产品方向，但会削弱“validate 可信”和“文件可追踪”的基础假设，因此需要在进入下一阶段记忆系统迭代前修复。

#### 修复内容

- 拒绝 durable topic 文件名与文件内 `- topic:` slug 不一致的 pack，避免导入后 `MEMORY.md` 索引指向不存在的 topic 文件。
- 校验 `working_context` payload 必须是 UTF-8 JSON object，且 `schema_version` 必须为 `working-context-v1`，`memory` 必须是 object。
- 拒绝 zip 内重复 archive entry，避免同名 payload 被 `zipfile` 读取语义掩盖。
- 导出 sessions/runs 时跳过 symlink 或解析后不在源目录内的状态文件，避免把仓库外文件打入 memory pack。

#### 验证结果

- `pytest tests/test_memory_pack.py -q`：14 passed。

#### 后续注意

- 后续新增 memory pack 模块时，必须同步补 validate schema，不允许“manifest hash 通过但 payload 结构不可解释”。
- `inspect` 和 `validate` 应保持同一安全边界；能被 inspect 的 pack 也必须先满足 validate 规则。

### 2026-05-05：Memory Pack v1 与文档同步门禁

#### 背景

Memory Pack v1 新增了用户可见的记忆迁移能力：REPL 入口 `/memory_pack` / `/memory-pack`，以及 advanced CLI `repo-harness memory export/import/inspect/validate`。这类能力同时影响用户文档、维护者 SOP、本地持久化边界和后续 roadmap，不能只通过代码和测试完成。

#### 修复内容

- 新增 `repo_harness/memory_pack.py`，使用标准库 zip/json/pathlib 实现本地 memory pack，不引入数据库、向量索引、后台服务或外部依赖。
- 更新 `repo_harness/cli.py`，加入 `/memory_pack` 菜单和 `repo-harness memory ...` advanced 子命令。
- 更新 README 和 `docs/getting-started.md`，说明 presets、导入导出命令和 `full-recovery` 隐私风险。
- 新增 `docs/maintainer-prep/memory-system-iteration-roadmap.md`，记录 Memory Pack v1 与后续记忆系统迭代边界。
- 更新维护者文档规则，把“文档同步”列为功能完成后的必需门禁。

#### 验证结果

- `uv run pytest -q`：126 passed。
- `uv run ruff check .`：通过。
- `python -m repo_harness memory --help`：通过。
- `.venv\Scripts\repo-harness.exe memory --help`：通过。

#### 后续注意

- 后续涉及 public CLI、REPL、state、memory、checkpoint、runs、安全边界或持久化格式的改动，都必须同步复盘 README、getting-started、architecture、review-pack 和 maintainer-prep 文档。
- 如果判断某个文档不需要改，应在修复摘要或提交说明中写明理由，避免未来维护者误以为遗漏。

### 2026-05-03：Windows 适配与工程化补强

#### 背景

本次修复由 Windows 环境验证触发，暴露出项目在跨平台兼容性、benchmark 可复现性、shell 执行语义和维护者文档管理上的问题。

Windows 是复现环境，不是根因本身。真正需要修复的是代码库中隐含的类 Unix 假设、宿主机状态依赖和缺失的文档资产。

#### 修复内容

##### 1. 缺少时区数据依赖声明

- 文件：[pyproject.toml](/C:/Users/Administrator/Desktop/cc/P1test/pyproject.toml:10)
- 现象：benchmark 和 evaluator 相关测试在真正执行前失败，因为 `ZoneInfo("Asia/Shanghai")` 在 Windows 上无法解析。
- 问题：项目实际依赖 IANA 时区数据，但没有声明 `tzdata` 依赖。
- 更正方式：把 `tzdata` 加入运行时依赖。
- 更正原因：这样可以把时区能力要求显式化，避免依赖宿主机是否自带时区数据。

##### 2. 可复现性元数据依赖宿主机 locale

- 文件：[pico/evaluator.py](/C:/Users/Administrator/Desktop/cc/P1test/pico/evaluator.py:121)
- 现象：benchmark 产物中的元数据会随着宿主机 locale 改变。
- 问题：所谓“可复现性”输出引用了机器当前 locale，而不是稳定约定值。
- 更正方式：为 benchmark 的可复现性元数据输出稳定 locale 值。
- 更正原因：同一份 benchmark 在不同电脑上应尽量产出可比较、可复核的结果。

##### 3. benchmark verifier 默认假设存在 `python3`

- 文件：[pico/evaluator.py](/C:/Users/Administrator/Desktop/cc/P1test/pico/evaluator.py:129)、[pico/evaluator.py](/C:/Users/Administrator/Desktop/cc/P1test/pico/evaluator.py:505)
- 现象：即使任务本身已正确完成，Windows 上 verifier 仍会失败。
- 问题：verifier 以 shell 字符串方式执行，并默认存在 `python3` 命令。
- 更正方式：识别 `python3 -c ...` 形式的 verifier，并改用 `sys.executable` 执行。
- 更正原因：当前解释器路径比依赖命令名更可靠，也更适合托管测试环境。

##### 4. shell 安全过滤误删 Windows 启动所需变量

- 文件：[pico/runtime.py](/C:/Users/Administrator/Desktop/cc/P1test/pico/runtime.py:512)
- 现象：shell 执行时报错，提示缺少 `%ComSpec%` 或 `%SystemRoot%`。
- 问题：过滤后的执行环境没有保留 Windows shell 启动所必需的基础变量。
- 更正方式：在过滤环境中保留 `ComSpec`、`SystemRoot` 和 `PATHEXT`。
- 更正原因：安全收敛应减少敏感暴露，但不能破坏 shell 的最小可运行条件。

##### 5. runtime 没有保证与命令语法兼容的 shell

- 文件：[pico/tools.py](/C:/Users/Administrator/Desktop/cc/P1test/pico/tools.py:65)、[pico/tools.py](/C:/Users/Administrator/Desktop/cc/P1test/pico/tools.py:220)
- 现象：使用 POSIX 引号和 `printf` 的命令在 Windows 默认 shell 下执行失败。
- 问题：测试和部分模型生成命令默认使用 POSIX shell 语义，但 runtime 实际交给平台默认 shell 处理。
- 更正方式：优先选择 POSIX 兼容 shell，并为常见 Git Bash 路径提供显式兜底。
- 更正原因：这能让执行语义与测试和命令本身隐含的 contract 保持一致。

##### 6. 测试依赖的文档骨架缺失

- 文件：
  - [docs/review-pack/README.md](/C:/Users/Administrator/Desktop/cc/P1test/docs/review-pack/README.md:1)
  - [docs/architecture/agent-harness-v1-overview.md](/C:/Users/Administrator/Desktop/cc/P1test/docs/architecture/agent-harness-v1-overview.md:1)
- 现象：测试套件因为找不到要求存在的文档而失败。
- 问题：仓库中缺少测试显式依赖的文档资产。
- 更正方式：补齐测试要求的文档骨架和基础内容。
- 更正原因：测试不应依赖缺失的受版本管理文件。

##### 7. 首次使用文档不够集中

- 文件：
  - [README.md](/C:/Users/Administrator/Desktop/cc/P1test/README.md:7)
  - [docs/getting-started.md](/C:/Users/Administrator/Desktop/cc/P1test/docs/getting-started.md:1)
- 现象：README 里已有安装和启动命令，但第一次使用者仍容易混淆项目根目录、PowerShell / CMD 环境变量、API Key 和 REPL 指令的边界。
- 问题：README 作为快速入口不适合承载完整新手教育；信息继续堆在 README 中会降低可读性。
- 更正方式：新增 `docs/getting-started.md`，并在 README 顶部和快速开始处加入入口链接。
- 更正原因：README 保持简洁，新手指南承接完整配置、使用技巧和产品化说明，维护成本更低。

#### 验证结果

- `uv run pytest tests/test_pico.py -q`：通过。
- `uv run ruff check .`：通过。
- `uv run pytest -q`：通过。
- Windows CMD / PowerShell 下 `uv run python -m pico --help`：通过。

#### 后续注意

- 如果后续执行 `RepoHarness` 全量重命名，本记录中的 `pico/`、`.pico/` 和 `uv run pico` 属于 2026-05-03 当时的历史事实，不应直接改写。
- 后续修复应继续追加新的日期记录，并在新记录中使用当时的当前包名、路径和命令。
