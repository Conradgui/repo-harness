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
