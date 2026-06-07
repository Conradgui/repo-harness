# 项目学习 SOP

## 文档目的

这份文档给新维护者一条理解 RepoHarness 的最短路径。目标不是逐文件通读，而是先抓住入口、runtime、工具、安全、记忆和验收体系。

文档健全是长期可维护性的一部分。功能完成后必须同步 README、docs/getting-started.md、维护者文档和 review pack。

## 当前公开入口

- CLI：`repo-harness`
- 模块入口：`python -m repo_harness`
- Python 包：`repo_harness`
- 本地状态目录：`.repo-harness/`

## 推荐阅读顺序

1. `README.md`：了解用户能力、配置方式和运行边界。
2. `docs/getting-started.md`：按操作级指南跑通 CLI、provider、sandbox、skills、workers 和 evidence。
3. `repo_harness/cli.py`：看参数解析、provider config、one-shot、REPL 分流。
4. `repo_harness/runtime.py`：看 `RepoHarness` 主循环、prompt、session、report。
5. `repo_harness/core/tool_executor.py`、`repo_harness/permissions.py`、`repo_harness/tool_policy.py`：看工具执行、安全和 trace metadata。
6. `repo_harness/features/skills.py`、`repo_harness/core/worker_manager.py`、`repo_harness/sandbox.py`：看 workflow 能力。
7. `repo_harness/memory.py`、`repo_harness/memory_pack.py`、`repo_harness/context_manager.py`：看记忆治理、pack 和检索解释。
8. `repo_harness/evaluation/run_evidence.py`、`repo_harness/release_evidence.py`、`scripts/run_business_scenario_dogfood.py`：看验收体系。

## 学习时必须确认的合同

- 配置优先级：CLI 显式参数 > process env / 项目 `.env` > 项目 `.repo-harness.toml` > 全局 config > 默认值。
- Tool execution 必须经过 permission、tool policy、sandbox 和 trace/report metadata。
- Skill `allowed_tools` 必须同时限制 prompt 和实际执行。
- Write worker 必须有 `write_scope`；Explore worker 只读。
- REPL、public CLI evidence 共用 runtime。
- Business dogfood 默认 fake/scripted provider，live 必须显式 opt-in。

## 记忆治理

```text
candidate fact -> Review Queue -> /memory review accept/edit -> durable topics
```

任何新功能只要会产生长期事实，都必须先进入 Review Queue。

## 推荐验证命令

```powershell
uv run python -m repo_harness --help
uv run repo-harness --help
uv run pytest tests -q --basetemp C:\tmp\rh-test
uv run ruff check .
git diff --check
```

## v6 新增能力速查

- **安全**：沙箱默认 `best_effort`；`run_shell` 危险命令黑名单；bubblewrap `--unshare-net`；`search` 防 ReDoS；evaluator verifier 白名单；secret regex 脱敏；session 持久化前脱敏；PATH 清理；TOCTOU 修复；`.env` 在 `.gitignore`；TOML 配置覆盖警告；`Path.is_relative_to()`；依赖版本上限。
- **稳定性**：所有工具加 `OSError`/`TimeoutExpired` 捕获；`SessionStore`/`RunStore`/`DurableMemoryStore` 原子写入；memory 损坏检测；context 预检自动压缩；滑动窗口重复调用守卫；`WorkerManager` TOCTOU 修复 + worker 超时。
- **可观测性**：`/metrics` 命令（工具统计、循环检测、热路径、失败率告警、token 消耗）；metrics 快照持久化。
- **编排**：`parallel()`、`pipeline()`、`dag()`、worker 间消息队列。
- **Auto Issue Fix**：5 stage 流水线 + 失败重试 + prompt injection 防护。

## 隐藏行为速查（维护者必读）

完整列表见 [architecture/agent-harness-v1-overview.md](../architecture/agent-harness-v1-overview.md) "运行时隐式行为"节。以下为调试时最容易踩坑的 10 项：

1. **Context overflow 自动压缩**：prompt 超限时静默压缩 history，用户无感知。
2. **Memory self-iteration 自动触发**：每次 turn 结束后自动推候选到 Review Queue。
3. **Tool Policy 隐式拒绝**：fresh read 要求、shell 搜索拦截、滑动窗口重复检测。
4. **delegate 强制只读**：子 agent 不能写文件、不能审批、不能再 delegate。
5. **run_shell bash 优先**：Windows 上也优先用 Git Bash，fallback 到 shell=True。
6. **search rg fallback**：rg 不可用时自动用 Python 遍历。
7. **Session 损坏降级**：JSON 解析失败返回空 session，不崩溃。
8. **被吞掉的异常**：6 处 `except Exception` 静默处理（见架构文档表格）。
9. **`/quit` 等价 `/exit`**：帮助文本只提到 `/exit`。
10. **`--trust-session`**：跳过所有 risky 工具审批，自动化场景用。
