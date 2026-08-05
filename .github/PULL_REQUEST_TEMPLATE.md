## 动机

为什么做这个改动？（如果修 bug，给出复现与根因；如果加功能，给出场景。）

## 改动内容

- 改动清单（每项一行，说明行为变化）

## 测试与验证

- [ ] 本地运行 `uv run ruff check .` 为 0 error
- [ ] 本地运行 `uv run pytest tests/ -q` 全绿
- [ ] 本地运行文档一致性测试全绿：`uv run pytest tests/test_docs_integrity.py tests/test_documented_snippets.py -q`
- [ ] 新增/修改了行为测试（项目遵循 ADR-003：测试只测行为，会 skip 的测试等于没测）

## 文档与 ADR

- [ ] 涉及行为或能力变化时，README / CHANGELOG 已同步
- [ ] 涉及设计取舍时，新增或更新了 ADR（`docs/decisions/`），并在本 PR 说明
- [ ] 文档数字均由命令复算得出（ADR-006），未手写"看起来好看"的指标

## 影响面与风险

- 涉及源码 / 测试 / 文档哪些部分？
- 是否会改变既有行为？是否影响向后兼容？
- 是否触碰安全边界（permission / sandbox / secret）？如果是，说明审查过程。

## Checklist

- [ ] 未削弱 `test_documented_snippets.py` / `test_docs_integrity.py`（反粉饰防线）
- [ ] 未删除既有能力（安全边界用开关而非删除，ADR-002）
