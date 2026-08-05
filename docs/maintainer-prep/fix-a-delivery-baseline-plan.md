# 修复 A：交付数字浮动基线缺陷

> 依据：codex 在 macOS/main 独立复核发现 `test_delivery_figures.py` 8 失败（7 个 delta 全 0），根因是 `measure.py` / `sync_figures.py` / `test_delivery_figures.py` 以浮动的 `origin/main` 作为 before baseline。本地（HEAD 领先 main）复现同类缺陷：P0/P1 新增 81 行源码后文档数字过期（source_lines 14,875 vs 14,794）。
> 用户铁律：数字必须由命令复算（ADR-006）；不得为看板改数字；测试只测行为（ADR-003）。

## 根因

- `measure.py:_commit_stats`（160-162 行）硬编码 `base="origin/main"`，产出 `commits_ahead_of_main`。
- `test_delivery_figures.py:baseline` fixture（30-40 行）执行 `measure.py origin/main`，baseline 缺失时 `pytest.skip`。
- `sync_figures.py:24` `BASELINE_REF = "origin/main"`。
- 当 `HEAD == origin/main`：`measured == baseline` → 所有 `delta` 全 0 → 7 个断言失败。
- 当源码新增文件未重跑 sync：`measured` 变化 → 文档数字过期 → 断言失败。

## 双 Agent 审核结论（已采纳）

- 审核员 A（APPROVE WITH FIXES）：A1 的 import 路径问题（scripts 非包）、A2 的 `measured["ref"]` 永不等于 `baseline["ref"]` 检测失效、macOS HEAD==baseline 场景应红而非绿。
- 审核员 B（REJECT，方向性问题）：实测确认 **531e02e 不是文档 before 列的真实基线**（531e02e=14,794/0 errors，文档 before=17,167/198 errors）——origin/main 已合并优化代码，不再代表"优化前"。delta 是**跨分支语义**（release/optimized-v1 相对 origin/main），固定 baseline 治不了 main 场景。
- **用户已决策：方向 3** —— baseline 用 `git merge-base(origin/main, HEAD)` 的分叉点 SHA（确定、可复算）；交付分支上 delta 断言校验；main 上（HEAD==merge-base）delta 断言 **skip**（无可校验的跨分支 delta）；baseline 无法测量 = fail 而非 skip。

## 修复（按方向 3）

### A1. baseline 改用 merge-base 分叉点

- `measure.py`：新增 `_merge_base(root)` 计算 `git merge-base origin/main HEAD`；`_commit_stats` 用它替代硬编码 `origin/main`，并输出 `baseline_sha`。
- `sync_figures.py`：`BASELINE_REF` 改为运行时计算 merge-base SHA。
- `test_delivery_figures.py`：`baseline` fixture 用 `measure.py <merge-base>`。

### A2. baseline 语义正确化

- `baseline` fixture：无法测量时 `pytest.fail`（基础设施坏了必须红）。
- delta 断言：当 `HEAD == merge-base`（main 上无跨分支语义）时 `pytest.skip`，并注明"no cross-branch delta to verify"。
- 交付分支上（HEAD 领先分叉点）：delta 断言正常校验。

### A3. 重跑 sync_figures.py

- 修改后运行 `python scripts/sync_figures.py`，用 merge-base 基线重算 delta，同步进 `docs/delivery/01-交付报告.md`。
- 文档散文层（"origin/main 为唯一 before 基线"、复现命令、before 列）同步更新为 merge-base 分叉点口径。

### A4. uv.lock

- 已确认锁定 pytest 9.1.1 / pytest-cov 7.1.0 / ruff 0.16.0，无需改动。

### A1. 引入不可变基线 ref（单一来源）

- 新增 `scripts/baseline_ref.py`，定义唯一常量 `BASELINE_REF`，指向一个**不可变 commit SHA**（取当前 `origin/main` 的 SHA `531e02e89411abc22de4c7377b51cbb3debeb438`），并注释说明更新规程。
- `measure.py` / `sync_figures.py` / `test_delivery_figures.py` 统一 `from baseline_ref import BASELINE_REF`，删除各自的硬编码。
- `measure.py` 的 `_commit_stats` 改用该常量（参数默认值），`commits_ahead_of_main` 语义变为"相对不可变基线的领先数"。

### A2. baseline 缺失或等于 HEAD 时 fail 而非 skip

- `test_delivery_figures.py:baseline` fixture：去掉 `pytest.skip`，改为 `pytest.fail`（baseline 无法测量 = 测试基础设施坏了，必须红）。
- 新增检查：若 `measured["ref"] == baseline["ref"]`（或 SHA 相等），`pytest.fail("baseline equals HEAD; deltas are meaningless")`，明确提示先跑 `sync_figures.py` 或更新 `baseline_ref.py`。

### A3. 修复后重跑 `sync_figures.py`

- 修改完成 A1/A2 后，运行 `python scripts/sync_figures.py`，把 P0/P1 引入的数字变更同步进 `docs/delivery/01-交付报告.md`（及任何带 measure/delta 标记的文件）。
- 确认 `measure.py` 输出的每个数字与文档一致（`test_delivery_figures.py` 全绿）。

### A4. 确认 `uv.lock` 固定版本

- 检查 `uv.lock` 存在且锁定 pytest / ruff / pytest-cov 版本（codex 建议 4）。
- 若 ruff 版本未锁（README 说 `ruff>=0.16.0,<0.17.0`），确认 lock 文件已固化具体版本。

## 门禁

```bash
uv run ruff check .
uv run pytest tests/test_delivery_figures.py tests/test_docs_integrity.py tests/test_documented_snippets.py -q
python scripts/sync_figures.py   # 输出 "N figure(s) updated" 后重跑测试全绿
```

## 红线

- 不删除 measure/delta 机制（ADR-006 依赖它）。
- 不改数字本身：只重跑 sync_figures.py 让数字跟随实测。
- baseline 是**不可变 SHA**，任何源码改动后若 delta 语义需要更新，走 sync 规程而非手改。
