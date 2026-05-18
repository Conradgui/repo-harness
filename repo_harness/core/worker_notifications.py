"""Worker notification helpers."""


def drain_notifications(worker_manager):
    return worker_manager.drain_notifications()


def format_notification(worker_id, status, result):
    return f"{worker_id} {status}: {result}"


def mark_drained(worker_manager, worker_id):
    for item in worker_manager.state.get("items", []):
        if item.get("id") == str(worker_id):
            item["notification_drained"] = True
            worker_manager._save()
            return dict(item)
    raise ValueError(f"unknown worker: {worker_id}")
