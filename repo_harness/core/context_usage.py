"""Context usage analysis for prompt governance."""

import unicodedata

DEFAULT_CONTEXT_WINDOW = 128000
AUTO_COMPACT_THRESHOLD = 0.84


def _count_cjk(text):
    """Count CJK characters in text (each typically 1-2 tokens)."""
    return sum(1 for ch in str(text) if unicodedata.category(ch).startswith("Lo"))


def estimate_tokens(text):
    """Estimate token count with CJK awareness.

    CJK characters average ~1.5 tokens each; ASCII ~0.25 tokens per char.
    This produces better estimates than plain chars/4 for mixed-language text.
    """
    text = str(text or "")
    if not text:
        return 0
    cjk = _count_cjk(text)
    non_cjk = len(text) - cjk
    return max(1, int(cjk * 1.5 + non_cjk * 0.25))


class ContextUsageAnalyzer:
    def __init__(self, runtime, context_window=None):
        self.runtime = runtime
        if context_window is None:
            context_window = getattr(runtime, "context_window", DEFAULT_CONTEXT_WINDOW)
        self.context_window = int(context_window)

    def analyze(self, rendered_or_metadata):
        if isinstance(rendered_or_metadata, dict) and "sections" in rendered_or_metadata:
            sections = rendered_or_metadata.get("sections", {})
            usage_sections = {}
            total_chars = 0
            for name, value in sections.items():
                chars = int(value.get("rendered_chars", value.get("chars", 0)) or 0)
                text = value.get("rendered_text", value.get("text", ""))
                total_chars += chars
                usage_sections[name] = {"chars": chars, "tokens": self._tokens_from_text(text, chars)}
        else:
            usage_sections, total_chars = self._sections_from_rendered(rendered_or_metadata)
        reserved_output = int(getattr(self.runtime, "max_new_tokens", 0) or 0)
        tool_chars = len(getattr(self.runtime, "prefix", "") or "")
        tool_text = str(getattr(self.runtime, "prefix", "") or "")
        total_tokens = sum(item["tokens"] for item in usage_sections.values())
        free_tokens = max(0, self.context_window - reserved_output - total_tokens)
        return {
            "estimation_method": "cjk_aware",
            "model": str(getattr(getattr(self.runtime, "model_client", None), "model", "")),
            "context_window": self.context_window,
            "reserved_output_tokens": reserved_output,
            "total_estimated_tokens": total_tokens,
            "free_tokens": free_tokens,
            "auto_compact_threshold": AUTO_COMPACT_THRESHOLD,
            "prompt_over_budget": total_tokens + reserved_output > self.context_window,
            "sections": usage_sections,
            "tools": {"chars": tool_chars, "tokens": estimate_tokens(tool_text)},
        }

    def _sections_from_rendered(self, rendered):
        usage_sections = {}
        total_chars = 0
        for name, value in (rendered or {}).items():
            text = str(getattr(value, "rendered", value) or "")
            chars = len(text)
            total_chars += chars
            usage_sections[str(name)] = {"chars": chars, "tokens": estimate_tokens(text)}
        return usage_sections, total_chars

    @staticmethod
    def _tokens_from_text(text, fallback_chars):
        """Estimate tokens from text if available, else fall back to chars/4."""
        if text:
            return estimate_tokens(text)
        return max(1, int(fallback_chars) // 4) if int(fallback_chars or 0) else 0
