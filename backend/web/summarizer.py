"""
web/summarizer.py — Mini IDE Milestone E

Condenses a fetched page's text down to the parts relevant to the
user's query, in the AI's own words (not reproduced verbatim).
"""
from __future__ import annotations

from llm.client import stream_chat

_SYSTEM = (
    "You are a research assistant. Given page text and a developer's "
    "question, extract ONLY the information relevant to answering it. "
    "Summarize in your own words — do not quote large passages. "
    "Keep it to 3-5 sentences. If the page doesn't answer the question, say so briefly."
)


async def summarize_for_query(
    page_text: str,
    query:     str,
    model:     str = "qwen3:8b",
) -> str:
    """Return a short, query-focused summary of page_text. Empty string on failure."""
    if not page_text.strip():
        return ""

    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": f"Question: {query}\n\nPage text:\n{page_text[:3_500]}"},
    ]

    full = ""
    try:
        async for token in stream_chat(model, messages, temperature=0.1, num_ctx=2048):
            full += token
            if len(full) > 800:
                break
    except Exception:
        return ""

    return full.strip()
