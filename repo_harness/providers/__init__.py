"""Provider compatibility layer used by the v3-style runtime engine."""

from .base import CompletionResult, complete_model
from .errors import ProviderError

__all__ = ["CompletionResult", "ProviderError", "complete_model"]
