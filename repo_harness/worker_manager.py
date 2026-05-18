"""Compatibility entrypoint for worker lifecycle management."""

from .core.worker_manager import WorkerManager, WorkerTask

__all__ = ["WorkerManager", "WorkerTask"]
