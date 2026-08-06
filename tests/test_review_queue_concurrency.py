"""Concurrent writes to the shared durable review queue must not lose records.

Parent and worker runtimes build separate LayeredMemory instances but point at
the same review-queue.jsonl (same workspace_root). Each run -- parent or child
-- calls promote_durable_memory at its end, so multiple threads can enqueue to
the same file concurrently. Without a module-level lock the read-modify-write
in enqueue loses updates: two threads load the same snapshot, each appends,
and the later full rewrite clobbers the earlier one.

These tests pin the fix: concurrent enqueues from distinct queue instances
(believable for parent + background workers) must all survive on disk.
"""

import threading

from repo_harness import memory as memorylib

DURABLE_TOPIC = "project-conventions"


def _enqueue_many(queue, worker_index, count, barrier):
    barrier.wait()
    for i in range(count):
        text = f"worker-{worker_index}-fact-{i}"
        queue.enqueue([(DURABLE_TOPIC, text)])


def test_concurrent_enqueues_from_distinct_instances_do_not_lose_records(tmp_path):
    # Distinct instances over the same root mimic parent + background workers.
    queue_a = memorylib.DurableMemoryReviewQueue(tmp_path)
    queue_b = memorylib.DurableMemoryReviewQueue(tmp_path)

    workers = 4
    per_worker = 10
    barrier = threading.Barrier(workers)
    threads = [
        threading.Thread(target=_enqueue_many, args=(queue_a if i % 2 == 0 else queue_b, i, per_worker, barrier))
        for i in range(workers)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    loaded = queue_a.load()
    texts = {record["text"] for record in loaded if record.get("status") == "pending"}
    expected = {f"worker-{w}-fact-{i}" for w in range(workers) for i in range(per_worker)}
    assert texts == expected, (
        f"lost {len(expected - texts)} record(s) under concurrent enqueue; "
        f"got {len(texts)}/{len(expected)}. The read-modify-write is not serialized."
    )


def test_mark_is_atomic_under_lock(tmp_path):
    queue = memorylib.DurableMemoryReviewQueue(tmp_path)
    queue.enqueue([(DURABLE_TOPIC, "one"), (DURABLE_TOPIC, "two")])

    def mark_one():
        queue.mark(queue.pending()[0]["id"], "accepted")

    threads = [threading.Thread(target=mark_one) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    loaded = queue.load()
    assert sum(1 for r in loaded if r.get("status") == "accepted") == 1
    assert sum(1 for r in loaded if r.get("status") == "pending") == 1
