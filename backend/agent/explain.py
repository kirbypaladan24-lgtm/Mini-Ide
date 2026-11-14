"""
agent/explain.py — Mini IDE Milestone E

On-demand explanation generator. Not run automatically on every
response (too expensive) — only when the user clicks "Why?" in the UI.
"""
from __future__ import annotations

from llm.client import stream_chat

_SYSTEM = (
    "You are explaining a code change you just proposed to a developer. "
    "Be concise — 2-3 sentences. Explain WHY this specific approach was "
    "chosen, referencing the actual code (existing patterns, libraries "
    "already in use, the specific request). If there's an obvious "
    "alternative approach, briefly mention it and why it wasn't used."
)


async def explain_change(
    request:  str,
    original: str,
    proposed: str,
    language: str,
    model:    str = "qwen3:8b",
) -> str:
    """Return a short explanation of why the change was made this way."""
    ext = language[:2] if language else ""
    user_msg = (
        f"Original request: {request}\n\n"
        f"Before:\n```{ext}\n{original[:2000]}\n```\n\n"
        f"After:\n```{ext}\n{proposed[:2000]}\n```\n\n"
        "Why was it implemented this way?"
    )
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",   "content": user_msg},
    ]

    full = ""
    try:
        async for token in stream_chat(model, messages, temperature=0.2, num_ctx=2048):
            full += token
            if len(full) > 600:
                break
    except Exception:
        return ""

    return full.strip()
