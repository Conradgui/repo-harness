from repo_harness.memory import LayeredMemory, summarize_read_result


def test_working_memory_tracks_summary_and_recent_files():
    memory = LayeredMemory()

    memory.set_task_summary("Investigate flaky tests")
    memory.remember_file("README.md")
    memory.remember_file("src/app.py")
    memory.remember_file("README.md")

    snapshot = memory.to_dict()

    assert snapshot["working"]["task_summary"] == "Investigate flaky tests"
    assert snapshot["working"]["recent_files"] == ["src/app.py", "README.md"]
    assert snapshot["task"] == "Investigate flaky tests"
    assert snapshot["files"] == ["src/app.py", "README.md"]


def test_episodic_notes_append_and_retrieve_deterministically():
    memory = LayeredMemory()

    memory.append_note("Exact tag note", tags=("recall",), created_at="2026-04-07T10:00:00+00:00")
    memory.append_note("Keyword overlap note about memory", created_at="2026-04-07T10:01:00+00:00")
    memory.append_note("Newest unrelated note", created_at="2026-04-07T10:02:00+00:00")
    memory.append_note("Older unrelated note", created_at="2026-04-07T09:59:00+00:00")

    snapshot = memory.to_dict()
    assert [note["text"] for note in snapshot["episodic_notes"]] == [
        "Exact tag note",
        "Keyword overlap note about memory",
        "Newest unrelated note",
        "Older unrelated note",
    ]
    assert snapshot["notes"] == [
        "Exact tag note",
        "Keyword overlap note about memory",
        "Newest unrelated note",
        "Older unrelated note",
    ]

    lines = [line for line in memory.retrieval_view("recall memory", limit=4).splitlines() if line.startswith("- ")]
    assert lines == [
        "- Exact tag note",
        "- Keyword overlap note about memory",
    ]


def test_file_summaries_use_canonical_paths_and_freshness(tmp_path):
    file_path = tmp_path / "sample.txt"
    file_path.write_text("alpha\n", encoding="utf-8")
    memory = LayeredMemory(workspace_root=tmp_path)

    memory.set_file_summary("./sample.txt", "sample.txt: alpha")
    memory.remember_file("./sample.txt")
    snapshot = memory.to_dict()["file_summaries"]["sample.txt"]

    assert snapshot["summary"] == "sample.txt: alpha"
    assert snapshot["freshness"]

    assert "sample.txt: alpha" in memory.render_memory_text()
    file_path.write_text("beta\n", encoding="utf-8")
    assert "sample.txt: alpha" not in memory.render_memory_text()

    memory.invalidate_file_summary("sample.txt")

    assert "sample.txt" not in memory.to_dict()["file_summaries"]


def test_python_read_summary_uses_bounded_structure():
    result = """# repo_harness/sample.py
import json
import os
from pathlib import Path

MAX_ITEMS = 3


class Runner:
    pass


def build():
    return Runner()


async def run():
    return build()
"""

    summary = summarize_read_result(result, complete_file=True)

    assert summary == "Python: imports=json,os,pathlib; classes=Runner; funcs=build,run; constants=MAX_ITEMS"
    assert len(summary) <= 180


def test_python_read_summary_caps_lists_and_total_length():
    result = """# many.py
import alpha
import beta
import gamma
import delta
import epsilon

FIRST = 1
SECOND = 2
THIRD = 3
FOURTH = 4

class One:
    pass

class Two:
    pass

class Three:
    pass

class Four:
    pass

def func_one():
    pass

def func_two():
    pass

def func_three():
    pass

def func_four():
    pass
"""

    summary = summarize_read_result(result, limit=140, complete_file=True)

    assert len(summary) <= 140
    assert summary.startswith("Python: ")
    assert "imports=alpha,beta,gamma (+2)" in summary
    assert "classes=One,Two,Three (+1)" in summary
    assert "funcs=func_one,func_two,func_three (+1)" in summary
    assert "constants=FIRST,SECOND,THIRD (+1)" not in summary
    assert "epsilon" not in summary
    assert "func_four" not in summary


def test_python_read_summary_falls_back_for_parse_errors_and_snippets():
    invalid_python = "# broken.py\nclass Broken(:\n    pass\n"
    snippet = "# broken.py\n    return value\n"
    syntactically_valid_prefix = "# sample.py\nimport json\n\nclass Partial:\n    pass\n"

    assert summarize_read_result(invalid_python, complete_file=True) == "class Broken(: | pass"
    assert summarize_read_result(snippet) == "return value"
    assert summarize_read_result(syntactically_valid_prefix) == "import json | class Partial: | pass"


def test_non_python_read_summary_keeps_legacy_first_lines():
    result = "# README.md\n# Title\nalpha\nbeta\ngamma\n"

    assert summarize_read_result(result) == "# Title | alpha | beta"


def test_markdown_read_summary_extracts_headings_and_ignores_fenced_code():
    result = """# docs/guide.md
# Guide

```python
# Not A Heading
```

## Setup
### Usage
"""

    summary = summarize_read_result(result, complete_file=True)

    assert summary == "Markdown: headings=Guide,Setup,Usage"
    assert len(summary) <= 180


def test_markdown_read_summary_preserves_title_hash_and_tracks_fence_length():
    result = '''# docs/csharp.md
# C#

````markdown
```
# Not A Heading
```
````

## Done
'''

    assert summarize_read_result(result, complete_file=True) == "Markdown: headings=C#,Done"


def test_markdown_read_summary_does_not_close_fence_with_trailing_text():
    result = """# docs/fence.md
```markdown
```not a close
# Still In Fence
```

# Done
"""

    assert summarize_read_result(result, complete_file=True) == "Markdown: headings=Done"


def test_markdown_partial_read_keeps_legacy_summary():
    result = "# docs/guide.md\n# Guide\nalpha\nbeta\n"

    assert summarize_read_result(result, complete_file=False) == "# Guide | alpha | beta"


def test_json_read_summary_extracts_top_level_object_keys_and_falls_back_for_malformed_json():
    result = '# package.json\n{"name":"demo","scripts":{},"dependencies":{}}\n'
    malformed = '# package.json\n{"name":\n'

    assert summarize_read_result(result, complete_file=True) == "Config: keys=name,scripts,dependencies"
    assert summarize_read_result(malformed, complete_file=True) == '{"name":'


def test_toml_ini_and_yaml_read_summaries_extract_shallow_structure():
    toml_result = (
        "# pyproject.toml\n"
        'requires-python = ">=3.11"\n'
        "[project]\n"
        'name = "demo"\n'
        "[tool.pytest.ini_options]\n"
        'addopts = "-q"\n'
    )
    ini_result = "# setup.cfg\n[tool:pytest]\naddopts = -q\n[flake8]\nmax-line-length = 100\n"
    yaml_result = "# workflow.yml\nname: CI\non:\n  push:\njobs:\n  test:\n"

    assert (
        summarize_read_result(toml_result, complete_file=True)
        == "Config: sections=project,tool.pytest.ini_options; keys=requires-python"
    )
    assert summarize_read_result(ini_result, complete_file=True) == "Config: sections=tool:pytest,flake8; keys=addopts,max-line-length"
    assert summarize_read_result(yaml_result, complete_file=True) == "Config: keys=name,on,jobs"


def test_python_test_file_summary_prefers_tests_over_generic_python_structure():
    result = """# tests/test_sample.py
import pytest

def helper():
    pass

def test_top_level():
    pass

class TestWorkflow:
    def helper(self):
        pass

    def test_runs(self):
        pass
"""

    summary = summarize_read_result(result, complete_file=True)

    assert summary == "Tests: tests=test_top_level,TestWorkflow.test_runs; classes=TestWorkflow"


def test_structured_read_summaries_keep_item_caps_and_limit():
    result = "# docs/guide.md\n# One\n# Two\n# Three\n# Four\n# Five\n# Six\n"

    summary = summarize_read_result(result, limit=60, complete_file=True)

    assert len(summary) <= 60
    assert summary == "Markdown: headings=One,Two,Three (+3)"


def test_process_notes_keep_kind_and_latest_duplicate_wins():
    memory = LayeredMemory()

    memory.append_note(
        "Shell partial success on README.md; inspect diff before retry",
        tags=("process", "partial_success"),
        created_at="2026-04-07T10:00:00+00:00",
        kind="process",
    )
    memory.append_note(
        "Shell partial success on README.md; inspect diff before retry",
        tags=("process", "partial_success"),
        created_at="2026-04-07T10:01:00+00:00",
        kind="process",
    )

    notes = memory.to_dict()["episodic_notes"]

    assert len(notes) == 1
    assert notes[0]["kind"] == "process"
    assert notes[0]["created_at"] == "2026-04-07T10:01:00+00:00"


def test_durable_memory_index_and_topic_notes_are_loaded_and_retrieved(tmp_path):
    memory_root = tmp_path / ".repo-harness" / "memory"
    topics_dir = memory_root / "topics"
    topics_dir.mkdir(parents=True)
    (memory_root / "MEMORY.md").write_text(
        "# Durable Memory Index\n\n"
        "- [project-conventions](topics/project-conventions.md): Project Conventions\n"
        "  - summary: Stable repository conventions.\n"
        "  - tags: convention\n",
        encoding="utf-8",
    )
    (topics_dir / "project-conventions.md").write_text(
        "# Project Conventions\n\n"
        "- topic: project-conventions\n"
        "- summary: Stable repository conventions.\n"
        "- tags: convention\n"
        "- updated_at: 2026-04-12T08:14:49+00:00\n\n"
        "## Notes\n"
        "- Use constrained tools instead of guessing.\n"
        "- Preserve local agent state under .repo-harness/.\n",
        encoding="utf-8",
    )

    memory = LayeredMemory(workspace_root=tmp_path)

    snapshot = memory.to_dict()
    assert snapshot["durable_topics"] == ["project-conventions"]

    lines = [line for line in memory.retrieval_view("constrained tools", limit=4).splitlines() if line.startswith("- ")]
    assert any("Use constrained tools instead of guessing." in line for line in lines)


def test_retrieval_explanations_are_deterministic_and_structured(tmp_path):
    memory_root = tmp_path / ".repo-harness" / "memory"
    topics_dir = memory_root / "topics"
    topics_dir.mkdir(parents=True)
    (memory_root / "MEMORY.md").write_text(
        "# Durable Memory Index\n\n"
        "- [project-conventions](topics/project-conventions.md): Governance Playbook\n"
        "  - summary: Stable repository conventions.\n"
        "  - tags: convention\n",
        encoding="utf-8",
    )
    (topics_dir / "project-conventions.md").write_text(
        "# Project Conventions\n\n"
        "- topic: project-conventions\n"
        "- summary: Stable repository conventions.\n"
        "- tags: convention\n"
        "- updated_at: 2026-04-12T08:14:49+00:00\n\n"
        "## Notes\n"
        "- Use constrained tools instead of guessing.\n",
        encoding="utf-8",
    )
    memory = LayeredMemory(workspace_root=tmp_path)
    memory.append_note(
        "Prefer constrained tools for repository edits.",
        tags=("convention",),
        source="session",
        created_at="2026-05-06T10:00:00+00:00",
    )

    first = memory.retrieval_explanations("Which convention covers constrained tools?", limit=3)
    second = memory.retrieval_explanations("Which convention covers constrained tools?", limit=3)

    assert first == second
    assert [item["text"] for item in first] == [
        "Prefer constrained tools for repository edits.",
        "Use constrained tools instead of guessing.",
    ]
    assert first[0]["kind"] == "episodic"
    assert first[0]["source"] == "session"
    assert first[0]["score"] > 0
    assert first[0]["score_breakdown"]["tag_match"] == 1
    assert first[0]["score_breakdown"]["keyword_overlap"] >= 2
    assert "recency" in first[0]["score_breakdown"]
    assert first[1]["kind"] == "durable"
    assert first[1]["source"] == "project-conventions"

    title_only = memory.retrieval_explanations("Governance Playbook", limit=3)
    assert [item["text"] for item in title_only] == ["Use constrained tools instead of guessing."]
    assert title_only[0]["kind"] == "durable"


def test_retrieval_explanations_empty_result_is_stable():
    memory = LayeredMemory()

    assert memory.retrieval_explanations("nothing matches this", limit=3) == []


def test_retrieval_normalizes_separated_and_camel_case_tokens():
    memory = LayeredMemory()
    memory.append_note(
        "Run memory_pack before moving stable state.",
        created_at="2026-05-07T10:00:00+00:00",
    )
    memory.append_note(
        "Open MemoryPack when preparing a portable archive.",
        created_at="2026-05-07T10:01:00+00:00",
    )

    hyphen_query = memory.retrieval_explanations("memory-pack", limit=3)
    spaced_query = memory.retrieval_explanations("memory pack", limit=3)

    assert [item["text"] for item in hyphen_query] == [
        "Open MemoryPack when preparing a portable archive.",
        "Run memory_pack before moving stable state.",
    ]
    assert [item["text"] for item in spaced_query] == [
        "Open MemoryPack when preparing a portable archive.",
        "Run memory_pack before moving stable state.",
    ]
    assert all(item["score_breakdown"]["keyword_overlap"] >= 2 for item in hyphen_query)


def test_durable_promotion_subject_key_ignores_joined_retrieval_tokens(tmp_path):
    memory = LayeredMemory(workspace_root=tmp_path)

    promoted, superseded = memory.promote_durable(
        [("dependency-facts", "memory pack is enabled.")]
    )
    assert promoted == ["dependency-facts: memory pack is enabled."]
    assert superseded == []

    promoted, superseded = memory.promote_durable(
        [("dependency-facts", "memory-pack is enabled.")]
    )

    dependency_path = tmp_path / ".repo-harness" / "memory" / "topics" / "dependency-facts.md"
    text = dependency_path.read_text(encoding="utf-8")
    assert promoted == ["dependency-facts: memory-pack is enabled."]
    assert superseded == [
        "dependency-facts: memory pack is enabled. -> memory-pack is enabled.",
    ]
    assert "memory-pack is enabled." in text
    assert "memory pack is enabled." not in text

    promoted, superseded = memory.promote_durable(
        [("dependency-facts", "MemoryPack is enabled.")]
    )

    text = dependency_path.read_text(encoding="utf-8")
    assert promoted == ["dependency-facts: MemoryPack is enabled."]
    assert superseded == [
        "dependency-facts: memory-pack is enabled. -> MemoryPack is enabled.",
    ]
    assert "MemoryPack is enabled." in text
    assert "memory-pack is enabled." not in text


def test_memory_organize_queues_candidates_without_writing_topics(tmp_path):
    from repo_harness import FakeModelClient, RepoHarness, SessionStore, WorkspaceContext

    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    agent = RepoHarness(
        model_client=FakeModelClient([]),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".repo-harness" / "sessions"),
        approval_policy="auto",
    )
    agent.memory.append_note("Preference: keep memory review-gated", source="test")
    agent.session["memory"] = agent.memory.to_dict()

    output = agent.memory_organize_text()

    assert "Memory organize" in output
    assert agent.memory_review_pending()
    topics_dir = tmp_path / ".repo-harness" / "memory" / "topics"
    assert not list(topics_dir.glob("*.md")) if topics_dir.exists() else True
