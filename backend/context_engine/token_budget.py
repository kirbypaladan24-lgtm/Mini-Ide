"""
context_engine/token_budget.py — Mini IDE Phase 3

Tracks the token budget for an LLM context window.
Uses char-count estimation (4 chars ≈ 1 token) — fast and good enough
for budgeting. Phase 4 can swap in tiktoken for precision.
"""

# Approximate context window sizes (in tokens) per model substring
# Updated 2026-08-27 to reflect available models
_WINDOWS: dict[str, int] = {
    "qwen2.5:1.5b":        8192,
    "qwen2.5":             8192,
    "qwen3:8b":            8192,
    "qwen3:4b":            8192,
    "qwen3":               8192,
    "llama3.2-vision":     8192,
    "llama3.2":            8192,
    "llama3":              8192,
    "huihui_ai_qwen2.5":   8192,
    "deepseek-coder":      8192,
    "deepseek":            8192,
    # legacy entries kept for backward compat
    "qwen2.5-coder-0.5b": 2048,
    "phi3:mini":           4096,
    "phi3":                4096,
}
_DEFAULT_WINDOW   = 4096
_CHARS_PER_TOKEN  = 4      # conservative
_SYSTEM_RESERVE   = 600    # tokens for system prompt + chat framing
_RESPONSE_RESERVE = 1200   # tokens left for the model to generate into


def _get_window(model: str) -> int:
    m = model.lower()
    for key, size in _WINDOWS.items():
        if key in m:
            return size
    return _DEFAULT_WINDOW


class TokenBudget:
    """
    Mutable budget object. Subtract from it as context layers are added.

    Usage:
        budget = TokenBudget("qwen3:8b")
        text = budget.trim(file_content)   # trim to fit
        budget.consume(text)               # mark as used
        if budget.remaining > 500:
            ...                            # add more context
    """

    def __init__(self, model: str):
        window      = _get_window(model)
        usable      = window - _SYSTEM_RESERVE - _RESPONSE_RESERVE
        self._limit = max(usable, 512) * _CHARS_PER_TOKEN
        self._used  = 0

    # ── Read ──────────────────────────────────────────────────────────────────
    @property
    def remaining(self) -> int:
        return max(0, self._limit - self._used)

    @property
    def used(self) -> int:
        return self._used

    # ── Mutations ─────────────────────────────────────────────────────────────
    def consume(self, text: str) -> None:
        """Mark chars as consumed."""
        self._used += len(text)

    def trim(
        self,
        text:      str,
        max_chars: int | None = None,
        reserve:   int        = 0,
    ) -> str:
        """
        Return text trimmed to fit within the remaining budget.

        Args:
            text:      The text to potentially trim.
            max_chars: Hard cap on returned length (applied first).
            reserve:   Extra chars to keep free for later items.
        """
        available = max(0, self.remaining - reserve)
        if max_chars is not None:
            available = min(available, max_chars)
        if len(text) <= available:
            return text
        cut = max(0, available - 80)
        return text[:cut] + "\n\n... [truncated to fit context window]"

    def fits(self, text: str) -> bool:
        return len(text) <= self.remaining
