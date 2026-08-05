# 贡献指南

感谢你愿意为 repo-harness 贡献代码。本文档是贡献者的单一入口：如何搭建开发环境、如何跑测试、提交 PR 前要满足什么。

## 开发环境

需要 Python 3.10+，推荐使用 `uv`：

```bash
uv sync
uv run python -m repo_harness --help
```

不依赖 `uv` 时也可以安装为可编辑包：

```bash
pip install -e .
repo-harness --help
```

## 质量门禁

所有改动在提交前必须本地全绿：

```bash
uv run ruff check .        # 0 error
uv run pytest tests/ -q    # 全量测试全绿
uv run pytest tests/test_docs_integrity.py tests/test_documented_snippets.py -q  # 文档一致性
```

### 文档一致性测试是硬性约束

`tests/test_docs_integrity.py` 校验所有被 git 跟踪的 markdown：内部链接必须指向真实存在的文件、文件不能为空。`tests/test_documented_snippets.py` 会真实执行文档中带 `<!-- verify:python -->` 标记的代码片段并断言退出码为 0。

**这两类测试是项目"报告反映现实、而不是现实迁就报告"的结构性防线。任何提交都不得削弱、删除或绕过它们。** 具体到实操：

- 新增 markdown 文件必须被 `git add` 跟踪（否则测试收集不到，本地绿但 CI 会不一致）。
- 新增 markdown 的内部链接只能指向真实存在的文件。
- 不要在文档里放未验证的 `<!-- verify:python -->` 代码块；要加就先确保它能真实运行。

## 代码风格

`pyproject.toml` 显式声明了 ruff 规则集，每个规则族都有入选理由。**只使用已声明的规则**，不要为了个别代码放宽或新增规则；确有必要时在 PR 里说明理由（参见 ADR-004 的背景）。

## 行为测试原则

项目遵循 ADR-003：测试断言行为，不断言行数、文档措辞或文件形状。新增功能时必须伴随能抓住该功能 bug 的测试——会 skip 的测试等于没测。

## PR 流程

1. 从 `main` 切出分支，命名如 `fix/<简述>`、`feat/<简述>`、`docs/<简述>`。
2. 提交信息用约定式前缀（`fix:`、`feat:`、`docs:`、`refactor:`、`test:`），简要说明动机。
3. 本地跑完全部质量门禁（见上）。
4. 打开 PR，填写 `.github/PULL_REQUEST_TEMPLATE.md` 的 checklist。
5. 涉及设计取舍或行为变更时，同步更新或新增 ADR（`docs/decisions/`），并在 PR 里说明。

## 文档维护约定

- 用户文档在 `docs/`（`getting-started.md`、`spec/`、`architecture/`）。
- 内部交付/评审文档（`docs/delivery/`、`docs/review-pack/`、`docs/maintainer-prep/`）是维护者视角的材料，默认不面向用户。
- 改动行为或新增能力时，README 与 changelog 要同步，但**文档数字必须由命令复算得出**（ADR-006），不允许手写"看起来好看"的指标。

## 求助

README 的"项目文档"一节索引了全部文档；架构细节见 `docs/architecture/agent-harness-v1-overview.md`；设计取舍见 `docs/decisions/README.md`。
