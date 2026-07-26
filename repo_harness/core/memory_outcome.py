"""Result of the memory work done during one turn.

These seven lists used to be seven separate attributes on RepoHarness, written
by two methods and read by two others. Bundling them gives the memory code a
single value to hand back, which is what lets it move out of the runtime class
without leaving a trail of attributes behind.
"""

from dataclasses import dataclass, field


@dataclass
class MemoryOutcome:
    """What the last durable-promotion and self-iteration passes produced."""

    durable_promotions: list = field(default_factory=list)
    durable_review_queued: list = field(default_factory=list)
    durable_rejections: list = field(default_factory=list)
    durable_superseded: list = field(default_factory=list)
    episodic_compactions: list = field(default_factory=list)
    self_iteration_review_queued: list = field(default_factory=list)
    self_iteration_rejections: list = field(default_factory=list)

    def record_durable_pass(self, *, queued, rejections):
        self.durable_promotions = []
        self.durable_review_queued = queued
        self.durable_rejections = rejections
        self.durable_superseded = []

    def record_self_iteration_pass(self, *, compactions, queued, rejections):
        self.episodic_compactions = compactions
        self.self_iteration_review_queued = queued
        self.self_iteration_rejections = rejections

    def self_iteration_dict(self):
        return {
            "episodic_compactions": list(self.episodic_compactions),
            "self_iteration_review_queued": list(self.self_iteration_review_queued),
            "self_iteration_rejections": list(self.self_iteration_rejections),
        }

    def report_dict(self):
        return {
            "durable_promotions": list(self.durable_promotions),
            "durable_review_queued": list(self.durable_review_queued),
            "durable_rejections": list(self.durable_rejections),
            "durable_superseded": list(self.durable_superseded),
            **self.self_iteration_dict(),
        }
