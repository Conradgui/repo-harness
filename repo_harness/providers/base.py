"""Provider-neutral completion helpers."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CompletionResult:
    text: str
    metadata: dict


def complete_model(model_client, prompt, max_new_tokens, **kwargs):
    result = model_client.complete(prompt, max_new_tokens, **kwargs)
    if isinstance(result, BaseException):
        raise result
    if isinstance(result, CompletionResult):
        return result
    metadata = dict(getattr(model_client, "last_completion_metadata", {}) or {})
    return CompletionResult(text=str(result), metadata=metadata)
