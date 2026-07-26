"""Contract for MemoryCoordinator, independent of RepoHarness.

The coordinator was extracted from the runtime and reaches back into it
through three callables. These tests exercise it with those callables faked,
which pins two things the integration suite cannot: that the callbacks are
invoked when they should be (and not when they should not), and that the
security filter on durable text holds without a whole agent standing behind
it.

Step 3 of the decomposition moves persistence into this seam. These are the
tests that will catch a regression when it does.
"""

from pathlib import Path

import pytest

from repo_harness import memory as memorylib
from repo_harness.core.memory_coordinator import MemoryCoordinator
from repo_harness.core.memory_outcome import MemoryOutcome


class Callbacks:
    """Records what the coordinator asked the runtime to do."""

    def __init__(self):
        self.persists = 0
        self.syncs = 0
        self.origins = []

    def persist(self):
        self.persists += 1

    def sync(self):
        self.syncs += 1

    def source_context(self, origin):
        self.origins.append(origin)
        return {"session_id": "s1", "run_id": "r1", "task_id": "t1", "origin": origin}


@pytest.fixture
def calls():
    return Callbacks()


@pytest.fixture
def coordinator(calls, tmp_path):
    memory = memorylib.LayeredMemory(
        memorylib.default_memory_state(), workspace_root=tmp_path
    )
    return MemoryCoordinator(
        memory,
        MemoryOutcome(),
        persist=calls.persist,
        sync=calls.sync,
        source_context=calls.source_context,
    )


class TestDurableTextFilter:
    """reject_durable_reason is the gate between a model's suggestion and the queue."""

    @pytest.mark.parametrize(
        "text,reason",
        [
            ("", "empty"),
            ("   ", "empty"),
            ("api_key = sk-abcdef123456", "secret_shaped"),
            ("the password is hunter2", "secret_shaped"),
            ("Current goal: ship the release", "transient_task_state"),
            ("当前卡点：provider 配置不对", "transient_task_state"),
            ("Traceback (most recent call last)", "noisy_output"),
            ("x" * 221, "noisy_output"),
        ],
    )
    def test_rejects_text_that_should_never_become_durable(self, coordinator, text, reason):
        assert coordinator.reject_durable_reason(text) == reason

    @pytest.mark.parametrize(
        "text",
        [
            "Project convention: tests live under tests/",
            "This repository targets Python 3.10 and above",
            "项目约定：提交信息用英文",
        ],
    )
    def test_accepts_durable_facts(self, coordinator, text):
        assert coordinator.reject_durable_reason(text) == ""

    def test_a_redacted_value_is_treated_as_secret_shaped(self, coordinator):
        assert coordinator.reject_durable_reason("token: <redacted>") == "secret_shaped"


class TestDurablePromotion:
    def test_promotion_requires_explicit_intent(self, coordinator, calls):
        promoted, rejected, superseded, queued = coordinator.promote_durable_memory(
            "what does this repo do?", "Project convention: tests live under tests/"
        )

        # No remember/save intent in the user message, so nothing is queued.
        assert queued == []
        assert promoted == []
        assert superseded == []
        assert calls.origins == ["durable-promotion"]

    def test_intent_queues_the_fact_for_review_rather_than_writing_it(
        self, coordinator, calls
    ):
        _, _, _, queued = coordinator.promote_durable_memory(
            "remember this", "Project convention: tests live under tests/"
        )

        assert queued, "an explicit remember should produce a queued candidate"
        # The point of the Review Queue: nothing reached durable topics.
        assert coordinator.memory_review_pending(), "candidate should be pending review"
        assert calls.persists == 1

    def test_secret_shaped_text_is_rejected_not_queued(self, coordinator):
        _, rejections, _, queued = coordinator.promote_durable_memory(
            "remember this", "Preference: my api_key is sk-abcdef123456"
        )

        assert queued == []
        assert rejections, "a rejection reason should be reported back"

    def test_outcome_records_the_pass(self, coordinator):
        coordinator.promote_durable_memory(
            "remember this", "Project convention: tests live under tests/"
        )

        assert coordinator.outcome.durable_review_queued
        # Promotion never writes durable topics directly, so these stay empty.
        assert coordinator.outcome.durable_promotions == []
        assert coordinator.outcome.durable_superseded == []


class TestReviewQueue:
    @pytest.fixture
    def queued_id(self, coordinator):
        coordinator.promote_durable_memory(
            "remember this", "Project convention: tests live under tests/"
        )
        pending = coordinator.memory_review_pending()
        assert pending
        return pending[0]["id"]

    def test_accept_promotes_and_persists(self, coordinator, calls, queued_id):
        before = calls.persists

        result = coordinator.memory_review_accept(queued_id)

        assert result["status"] == "accepted"
        assert calls.persists == before + 1
        assert not coordinator.memory_review_pending()

    def test_edit_rewrites_the_record(self, coordinator, queued_id):
        result = coordinator.memory_review_edit(
            queued_id, topic="project-conventions", text="Tests live under tests/"
        )

        assert result["status"] == "accepted"

    def test_edit_still_applies_the_security_filter(self, coordinator, queued_id):
        result = coordinator.memory_review_edit(
            queued_id, topic="project-conventions", text="api_key = sk-abcdef123456"
        )

        assert result["status"] == "rejected"
        assert result["reason"] == "secret_shaped"

    def test_reject_drops_the_candidate(self, coordinator, queued_id):
        result = coordinator.memory_review_reject(queued_id)

        assert result["status"] == "rejected"
        assert not coordinator.memory_review_pending()

    def test_skip_leaves_the_candidate_pending(self, coordinator, calls, queued_id):
        before = calls.persists

        result = coordinator.memory_review_skip(queued_id)

        # Skip reports the record's state, not the action -- it stays pending.
        assert result["status"] == "pending"
        assert coordinator.memory_review_pending(), "skip must not consume the candidate"
        # Nothing changed, so nothing should be written.
        assert calls.persists == before

    def test_unknown_record_id_is_reported_not_raised(self, coordinator):
        result = coordinator.memory_review_accept("does-not-exist")

        assert result["status"] != "accepted"


class TestSelfIteration:
    def test_reports_an_empty_pass_without_persisting(self, coordinator, calls):
        before = calls.persists

        result = coordinator.run_memory_self_iteration()

        assert result["episodic_compactions"] == []
        # Nothing changed, so the session is not rewritten.
        assert calls.persists == before

    def test_status_exposes_the_last_pass_and_pending_count(self, coordinator):
        coordinator.run_memory_self_iteration()

        status = coordinator.memory_self_iteration_status()

        assert set(status) == {
            "episodic_compactions",
            "self_iteration_review_queued",
            "self_iteration_rejections",
            "pending_review_count",
        }
        assert status["pending_review_count"] == 0

    def test_status_counts_pending_candidates(self, coordinator):
        coordinator.promote_durable_memory(
            "remember this", "Project convention: tests live under tests/"
        )

        assert coordinator.memory_self_iteration_status()["pending_review_count"] == 1

    def test_text_renderings_do_not_raise_on_an_empty_memory(self, coordinator):
        assert isinstance(coordinator.memory_self_iteration_text(), str)
        assert isinstance(coordinator.memory_organize_text(), str)


class TestRuntimeSeam:
    """The three callbacks are the whole dependency on RepoHarness."""

    def test_source_context_stamps_the_origin(self, coordinator, calls):
        coordinator.promote_durable_memory("remember this", "Project convention: x")
        coordinator.run_memory_self_iteration()

        assert "durable-promotion" in calls.origins

    def test_coordinator_does_not_import_the_runtime(self):
        from repo_harness.core import memory_coordinator as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        # A back-reference would make the dependency circular and undo the point
        # of the extraction.
        assert "from ..runtime" not in source
        assert "import runtime" not in source
