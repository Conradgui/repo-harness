# 版本管理说明

## 建议分支名

- `codex/cross-platform-hardening`

## 建议提交分组

1. `fix: declare timezone data dependency and stabilize benchmark verifier execution`
2. `fix: harden shell execution for Windows portability`
3. `docs: add maintainer prep and required review skeletons`

## 建议评审清单

- 执行 `python -m uv sync`
- 执行 `python -m uv run ruff check .`
- 执行 `python -m uv run pytest -q`
- 如果条件允许，分别在至少一台 Windows 机器和一台类 Unix 环境上确认 benchmark 产物稳定

## 建议上游提交摘要

- 说明 Windows 只是把仓库中已有的可移植性假设复现出来。
- 区分“环境触发条件”和“代码库根因”。
- 明确指出 benchmark 的可复现性约束和 shell 执行 contract 在修复前定义不足。
