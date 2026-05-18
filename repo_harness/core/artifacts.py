"""Runtime artifact helpers."""


def changed_paths(runtime):
    return list(getattr(runtime, "_run_changed_paths", []))

