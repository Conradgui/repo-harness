"""Bundled RepoHarness skills."""

from .skills import Skill


def bundled_skills():
    return [
        Skill(
            name="review",
            description="Review changes for correctness, safety, and missing tests.",
            source="builtin",
            when_to_use="Use before committing non-trivial code changes.",
            context="inline",
            allowed_tools=("read_file", "search", "list_files"),
            prompt=(
                "Review $ARGUMENTS or the current change set. Focus on bugs, regressions, "
                "missing tests, and RepoHarness memory governance. Do not write durable memory."
            ),
        ),
        Skill(
            name="test",
            description="Plan and run focused verification for a change.",
            source="builtin",
            when_to_use="Use when deciding which tests should prove a change.",
            context="inline",
            allowed_tools=("read_file", "search", "run_shell"),
            prompt=(
                "Create and execute a focused verification plan for $ARGUMENTS. Prefer existing "
                "project test commands. Report exact commands and outcomes."
            ),
        ),
        Skill(
            name="commit",
            description="Prepare a commit summary after verification.",
            source="builtin",
            when_to_use="Use after tests pass and before creating a commit.",
            context="inline",
            allowed_tools=("read_file", "search", "run_shell"),
            prompt=(
                "Inspect the staged and unstaged changes for $ARGUMENTS, summarize the scope, "
                "and propose a concise commit message. Do not modify files."
            ),
        ),
        Skill(
            name="simplify",
            description="Simplify an implementation without changing behavior.",
            source="builtin",
            when_to_use="Use when code works but is more complex than needed.",
            context="inline",
            allowed_tools=("read_file", "search", "patch_file"),
            prompt=(
                "Simplify $ARGUMENTS while preserving behavior. Read relevant files first, "
                "make minimal patches, and keep memory writes review-gated."
            ),
        ),
    ]


BUNDLED_SKILLS = {skill.name: skill.metadata() for skill in bundled_skills()}
