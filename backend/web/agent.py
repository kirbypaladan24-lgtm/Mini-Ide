"""
web/agent.py — Mini IDE Milestone E

Decides when web research is actually warranted (never on every message)
and orchestrates search → fetch → summarize into a single context block.
"""
from __future__ import annotations

import re

from web.search     import web_search, SEARCH_OK
from web.browser     import fetch_page
from web.extractor   import extract_text
from web.summarizer  import summarize_for_query

# ── Trigger detection ──────────────────────────────────────────────────────────
_EXPLICIT_TRIGGERS = re.compile(
    r"\b(latest|current|newest|recent|up[\s-]?to[\s-]?date)\s+(version|release|docs?|documentation)\b"
    r"|\bhow does\s+\w+\s+(api|service|library|package)\s+work\b"
    r"|\bsearch (the web|online|for)\b"
    r"|\bwhat'?s new in\b",
    re.IGNORECASE,
)


def should_use_web(user_message: str) -> bool:
    """
    Decide whether this message warrants a web search.
    Conservative — only fires on explicit recency/external-info signals,
    never on every chat turn.
    """
    if not SEARCH_OK:
        return False
    return bool(_EXPLICIT_TRIGGERS.search(user_message))


# ── Orchestration ────────────────────────────────────────────────────────────
async def run_web_research(
    query: str,
    model: str = "qwen3:8b",
    max_results: int = 3,
) -> dict:
    """
    Run the full pipeline: search → fetch top results → summarize.
    Returns {"used": bool, "context": str, "sources": [{title, url}]}
    context is empty string if nothing useful was found.
    """
    results = await web_search(query, max_results=max_results)
    if not results:
        return {"used": False, "context": "", "sources": []}

    summaries: list[str] = []
    sources:   list[dict] = []

    for r in results[:max_results]:
        html = await fetch_page(r["url"])
        text = extract_text(html) if html else r["snippet"]
        if not text:
            continue

        summary = await summarize_for_query(text, query, model)
        if not summary:
            summary = r["snippet"][:200]

        summaries.append(f"From {r['title']} ({r['url']}):\n{summary}")
        sources.append({"title": r["title"], "url": r["url"]})

    if not summaries:
        return {"used": False, "context": "", "sources": []}

    context = "### Web research results:\n\n" + "\n\n".join(summaries)
    return {"used": True, "context": context, "sources": sources}
