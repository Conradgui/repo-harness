# OSS 成熟度加固执行计划（P0 / P1 / P2）

> 目标：在不破坏 repo-harness 既有工程纪律（ADR 体系、反粉饰文档测试、fail-closed 安全哲学、显式 lint 规则集）的前提下，补齐"可被严肃开源社区接纳"的最后一公里。
> 总原则：**先文档/配置，后代码重构；每阶段以全量测试 + ruff + 文档一致性测试为门禁；任何源码改动必须有独立工程理由（与看板无关）。**
> 计划修订（双 Agent 审核 APPROVE WITH FIXES 后）：
> - **R1 已修**：不把版本号改 0.7.0。文档 v1–v7 是内部迭代代号，与 PyPI 版本是两套语义；仓库未发布过任何版本，首个公开版本保留 0.1.x，CHANGELOG 记录 v1–v7 为开发史。
> - **R2/R6 已修**：P1-1 收敛为"仅 CLI 三个 if 注册表化"（零行为变更）；"REPL slash 复用同一路由"降级为 P2，因 /memory 与 CLI memory 行为完全不同，统一是无行为依据的重构。
> - **R3 已修**：changelog 提升保留 `docs/maintainer-prep/changelog-draft.md` 旧文件不删（避免断链），README 链接改指根 CHANGELOG.md。
> - **R4 已修**：版本不改动，`memory_pack.py:939` 回退值保持 0.1.0，与 pyproject 一致。
> - 新增 md 三条防红约束：内部链接必须指向真实存在文件 / 不得含未验证的 `<!-- verify:python -->` 块 / 非空；且必须 git add 跟踪（test_docs_integrity 依赖 git ls-files）。
> - --cov-fail-under 阈值必须先实测 3.10–3.13 四版本真实覆盖率再定，写入注释来源。
> - pre-commit 的 ruff hook 必须沿用 pyproject 显式规则集（ADR-004）。
> - CONTRIBUTING 含"贡献者不得削弱 test_documented_snippets / test_docs_integrity"显式约束。
> - RELEASING.md 放根目录（与 CONTRIBUTING/SECURITY 并列）。
> - 删除残留文件（_check_mermaid.py / project-review-report.html）前先 grep 确认无引用并定 gitignore 策略。

## P0：社区门面件 + 元数据 + CI 门禁（纯新增/低风险，不动版本号）

1. 根目录新增 `CONTRIBUTING.md` — 从 docs/maintainer-prep 提炼：dev setup（uv sync）、测试命令、ruff 规则引用（pyproject 显式声明）、PR 流程、ADR 更新要求、文档一致性测试（test_docs_integrity / test_documented_snippets）说明。
2. 根目录新增 `SECURITY.md` — 漏洞上报渠道（GitHub Security Advisory + 邮箱占位）、支持版本、披露政策。诚实声明 sandbox 边界（引用 ADR-007：read_only 阻断 run_shell，命令字符串过滤非安全边界）。
3. 根目录新增 `CODE_OF_CONDUCT.md` — 采用 Contributor Covenant v2.1（MIT 项目标准）。
4. 根目录新增 `CHANGELOG.md` — 从 docs/maintainer-prep/changelog-draft.md 提升，按 Keep a Changelog 规范（Unreleased + 已发布版本锚点），保留全部 v1–v7 历史。
5. `pyproject.toml` 补元数据：`classifiers`（MIT、Python 3.10–3.13、Topic）、`keywords`、`[project.urls]`（Homepage/Repository/Issues）；`readme = "README.md"`。
6. 新增 `.github/ISSUE_TEMPLATE/bug_report.md` + `feature_request.md`（含环境信息、最小复现、行为/期望）。
7. 新增 `.github/PULL_REQUEST_TEMPLATE.md`（含测试/文档/lint/ADR checklist）。
8. 版本策略：**保留 `0.1.0`**（首个公开版本从 0.x 起步是工程事实；CHANGELOG 记录 v1–v7 为开发史，不把文档迭代代号伪装成发布版本）。确认 `memory_pack.py:939` 回退值仍为 0.1.0 与 pyproject 一致。
9. 新增根目录 `RELEASING.md`（发布流程：semver 规则、tag 约定、CHANGELOG 更新、PyPI 后续步骤；与 CONTRIBUTING/SECURITY 并列）。
10. `.circleci/config.yml` 测试命令加 `--cov-fail-under`：先实测 3.10–3.13 四版本真实覆盖率，取四者最小值再定阈值（避免个别版本 CI 红），阈值与来源写入注释。

## P1：架构健康度 + 可观测 + 文档受众分区（含源码改动，须过审核）

1. `cli.py` 命令注册表化（最小范围）：消除 `main()` 内三个 `if raw_argv[0]==` 硬分流（memory/provider/auto-issue-fix），建立 `COMMANDS` 注册表。**纯重构、零行为变更**（现有 `main(["memory",...])` 分流断言测试兜底）。REPL slash 命令复用同一路由**不在本轮**——/memory 与 CLI memory 行为不同，统一路由是 P2 独立任务，须先立行为基线。
2. 从零引入 `logging` 诊断通道：新增 `repo_harness/logging_config.py`，默认 WARNING（基本静默），`REPO_HARNESS_LOG_LEVEL` 可调；走 stderr/独立 handler，**不改变 rich 终端渲染与 trace.jsonl 语义**；先覆盖纯函数错误路径，渐进接入。
3. 新增 `docs/api-stability.md`：明确 stable public API（RepoHarness/ask/build_agent/main）vs internal；0.x 兼容预期；弃用策略（--tui 先例）。
4. README 文档受众分区：顶部加一小节区分"用户文档 / 维护者文档 / 内部交付"三类链接（不删除 delivery/review-pack 等，只分区标注）。
5. README 顶部加 Badge（shields.io：Python 版本、License、pytest、ruff）。**图片来自 shields.io 静态 badge，无外网资源依赖，离线可渲染为文本链接。**
6. 新增 `Makefile`（lint/test/typecheck/fmt 目标）+ `.pre-commit-config.yaml`（ruff + 文件尾换行）。
7. `py.typed` 空文件 + `[tool.setuptools.package-data]` 声明（PEP 561）。

## P2：长期健康度（后续迭代，本轮收尾即可，不阻塞）

1. 英文 README（`README.en.md`）或英文 getting-started —— 视用户接受度推进。
2. `RepoHarness` 能力下沉为组合对象（MemoryReviewAPI/SkillAPI 等），进一步压低 1196 行主类。
3. trace span 树（`parent_span_id`），支持 worker 调用链追溯。
4. 脱敏双保险（键名正则 + 值匹配）。
5. mutation testing / property-based 测试，验证测试有效性（呼应 ADR-003）。
6. 清理工作区残留：`_check_mermaid.py`（临时文件）、`project-review-report.html`（评审产物，确认 gitignore 策略）。

## 门禁（每阶段必须全绿）

```bash
uv run ruff check .        # 0 error
uv run pytest tests/ -q    # 509 passed / 1 skipped 基线（P1 后不得少于）
uv run pytest tests/test_docs_integrity.py tests/test_documented_snippets.py -q  # 文档一致性
```

## 红线

- 不删除既有能力，不改坏测试；源码改动必须通过"即使没有看板，我还会做这个改动吗"自问。
- 不削弱 `test_documented_snippets.py` / `test_docs_integrity.py`（反粉饰防线）。
- ADR 记录的决策不被推翻（除非新增 ADR 说明理由）。
- 每阶段完成后独立验收 Agent 复核。
