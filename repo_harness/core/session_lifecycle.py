"""Session lifecycle helpers."""


def save_session(runtime):
    runtime.session_path = runtime.session_store.save(runtime.session)
    return runtime.session_path

