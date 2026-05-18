"""Runtime secret redaction helpers."""


def redact(runtime, value):
    return runtime.redact_artifact(value)

