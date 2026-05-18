"""Runtime checkpoint helpers."""


def create_checkpoint(runtime, task_state, user_message, trigger):
    return runtime.create_checkpoint(task_state, user_message, trigger=trigger)
