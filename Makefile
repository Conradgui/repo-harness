# repo-harness developer convenience targets.
# The CI (CircleCI) runs the same commands; keep them in sync.
# Prefer `uv run` so the pinned toolchain is used everywhere.

.PHONY: help install lint format test typecheck docs check

help:
	@echo "Targets:"
	@echo "  install    uv sync (dev dependencies)"
	@echo "  lint       ruff check . (0 error expected)"
	@echo "  format     ruff format --check ."
	@echo "  test       full pytest suite with coverage report"
	@echo "  docs       documentation integrity + snippet tests"
	@echo "  typecheck  (placeholder) mypy/pyright baseline -- not yet enforced"
	@echo "  check      lint + docs + test"

install:
	uv sync

lint:
	uv run ruff check .

format:
	uv run ruff format --check .

test:
	uv run pytest tests/ -q --tb=short --cov=repo_harness --cov-report=term-missing

docs:
	uv run pytest tests/test_docs_integrity.py tests/test_documented_snippets.py -q

typecheck:
	@echo "No static type check is enforced yet; see docs/api-stability.md for status."

check: lint docs test
