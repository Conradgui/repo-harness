"""Context usage analysis for prompt governance."""


DEFAULT_CONTEXT_WINDOW = 128000
AUTO_COMPACT_THRESHOLD = 0.84


class ContextUsageAnalyzer:
    def __init__(self, runtime, context_window=DEFAULT_CONTEXT_WINDOW):
        self.runtime = runtime
        self.context_window = int(context_window)

    def analyze(self, rendered_or_metadata):
        if isinstance(rendered_or_metadata, dict) and "sections" in rendered_or_metadata:
            sections = rendered_or_metadata.get("sections", {})
            usage_sections = {}
            total_chars = 0
            for name, value in sections.items():
                chars = int(value.get("rendered_chars", value.get("chars", 0)) or 0)
                total_chars += chars
                usage_sections[name] = {"chars": chars, "tokens": self._tokens(chars)}
        else:
            usage_sections, total_chars = self._sections_from_rendered(rendered_or_metadata)
        reserved_output = int(getattr(self.runtime, "max_new_tokens", 0) or 0)
        tool_chars = len(getattr(self.runtime, "prefix", "") or "")
        total_tokens = sum(item["tokens"] for item in usage_sections.values())
        free_tokens = max(0, self.context_window - reserved_output - total_tokens)
        return {
            "estimation_method": "chars_div_4",
            "model": str(getattr(getattr(self.runtime, "model_client", None), "model", "")),
            "context_window": self.context_window,
            "reserved_output_tokens": reserved_output,
            "total_estimated_tokens": total_tokens,
            "free_tokens": free_tokens,
            "auto_compact_threshold": AUTO_COMPACT_THRESHOLD,
            "prompt_over_budget": total_tokens + reserved_output > self.context_window,
            "sections": usage_sections,
            "tools": {"chars": tool_chars, "tokens": self._tokens(tool_chars)},
        }

    def _sections_from_rendered(self, rendered):
        usage_sections = {}
        total_chars = 0
        for name, value in (rendered or {}).items():
            text = getattr(value, "rendered", value)
            chars = len(str(text or ""))
            total_chars += chars
            usage_sections[str(name)] = {"chars": chars, "tokens": self._tokens(chars)}
        return usage_sections, total_chars

    @staticmethod
    def _tokens(chars):
        return max(1, int(chars) // 4) if int(chars or 0) else 0
