"""G3: multilingual source text and English canonical text must be separate.

The contract: a review record keeps the multilingual source_text as evidence
and an English canonical_text for durable memory + ASCII retrieval. A Chinese
candidate is allowed into the queue (the user interacts in Chinese) but it is
flagged canonical_needs_review. Accepting it into durable memory requires an
English canonical (or a retrievable mixed form) -- raw Chinese is never
silently promoted, otherwise the write/retrieval contract gap stays open.

Some tests assert the current behaviour and fail until the implementation
lands.
"""

import json

from repo_harness import memory as memorylib


def _queue(tmp_path):
    return memorylib.DurableMemoryReviewQueue(tmp_path)


def test_chinese_candidate_keeps_source_and_marks_canonical_needs_review(tmp_path):
    queue = _queue(tmp_path)
    queued = queue.enqueue([("project-conventions", "项目约定：提交信息用英文")])

    assert queued, "chinese candidate must be enqueued"
    record = queued[0]
    assert record["source_text"] == "项目约定：提交信息用英文"
    assert record["canonical_text"] is not None
    assert record["canonical_needs_review"] is True


def test_ascii_candidate_canonical_equals_text(tmp_path):
    queue = _queue(tmp_path)
    queued = queue.enqueue([("project-conventions", "Use conventional commits.")])

    record = queued[0]
    assert record["canonical_text"] == "Use conventional commits."
    assert record["source_text"] == "Use conventional commits."
    assert record["canonical_needs_review"] is False


def test_accept_without_edit_blocks_non_ascii_canonical(tmp_path):
    # Core G3 path: accepting a Chinese candidate without editing in an
    # English canonical must be blocked. Raw Chinese never reaches durable.
    memory = memorylib.LayeredMemory(memorylib.default_memory_state(), workspace_root=tmp_path)
    memory.enqueue_durable_reviews([("project-conventions", "提交信息必须用英文")])

    pending = memory.pending_durable_reviews()
    assert pending, "candidate must be pending"
    record = pending[0]
    assert record["canonical_needs_review"] is True

    # Accept without an English canonical must be rejected, not silent.
    result = memory.accept_durable_review(record["id"])
    assert result[0] is None, "accept of non-ASCII canonical without edit must be blocked"

    notes = memorylib.DurableMemoryStore(tmp_path / ".repo-harness" / "memory").load_topic_notes("project-conventions")
    assert not notes, "durable memory must not contain the uncanonicalized Chinese note"


def test_accept_promotes_canonical_not_source(tmp_path):
    # After the user edits in an English canonical, accept promotes that
    # canonical into durable memory -- not the Chinese source.
    memory = memorylib.LayeredMemory(memorylib.default_memory_state(), workspace_root=tmp_path)
    memory.enqueue_durable_reviews([("project-conventions", "使用英文提交信息")])

    pending = memory.pending_durable_reviews()
    record = pending[0]

    updated, promoted, _ = memory.accept_durable_review(
        record["id"], topic="project-conventions", text="Use English for commit messages."
    )
    assert updated is not None
    assert any("Use English for commit messages." in str(note) for note in promoted or []), (
        "durable memory must be written from the canonical text"
    )


def test_edit_canonical_keeps_source_text(tmp_path):
    queue = _queue(tmp_path)
    queued = queue.enqueue([("project-conventions", "决策：使用 pytest")])
    record_id = queued[0]["id"]

    updated = queue.update_pending(record_id, text="Decision: use pytest for tests.")
    assert updated is not None
    assert updated["source_text"] == "决策：使用 pytest"
    assert updated["canonical_text"] == "Decision: use pytest for tests."


def test_old_record_without_canonical_fields_migrates(tmp_path):
    # A record persisted before canonical/source fields existed must load
    # safely: canonical defaults to text; a Chinese legacy record gets the
    # needs_review flag (never silently treated as already canonical).
    queue = _queue(tmp_path)
    queue.enqueue([("project-conventions", "legacy english fact")])
    queue.enqueue([("project-conventions", "旧中文事实")])

    # Simulate an old file: strip the new fields from every line.
    path = queue.path
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for line in lines:
        line.pop("canonical_text", None)
        line.pop("source_text", None)
        line.pop("canonical_needs_review", None)
    path.write_text("\n".join(json.dumps(line, ensure_ascii=False) for line in lines) + "\n", encoding="utf-8")

    loaded = queue.load()
    english = next(r for r in loaded if r.get("text") == "legacy english fact")
    assert english.get("canonical_text") == "legacy english fact"
    assert english.get("canonical_needs_review") is False

    chinese = next(r for r in loaded if r.get("text") == "旧中文事实")
    assert chinese.get("canonical_text") == "旧中文事实"
    assert chinese.get("canonical_needs_review") is True


def test_durable_retrieval_uses_canonical(tmp_path):
    memory = memorylib.LayeredMemory(memorylib.default_memory_state(), workspace_root=tmp_path)
    memory.enqueue_durable_reviews([("project-conventions", "提交信息必须用英文")])
    pending = memory.pending_durable_reviews()
    record = pending[0]
    memory.accept_durable_review(record["id"], topic="project-conventions", text="Commit messages must be in English.")

    notes = memorylib.DurableMemoryStore(tmp_path / ".repo-harness" / "memory").load_topic_notes("project-conventions")
    assert notes, "durable note must exist"
    assert any("English" in note.get("text", "") for note in notes)


def test_mixed_ascii_retrievable_canonical_allowed(tmp_path):
    # A mixed Chinese/English canonical that ASCII retrieval can still hit
    # (has English tokens) is a legitimate exception: the retrieval contract
    # still holds. This is machine-decidable, not a user preference.
    memory = memorylib.LayeredMemory(memorylib.default_memory_state(), workspace_root=tmp_path)
    memory.enqueue_durable_reviews([("project-conventions", "提交信息必须用 English commit messages")])

    pending = memory.pending_durable_reviews()
    record = pending[0]
    updated, promoted, _ = memory.accept_durable_review(record["id"])
    assert updated is not None, "retrievable mixed canonical may be accepted"
    assert any("English commit messages" in str(note) for note in promoted or [])
