"""
web/search.py — Mini IDE Milestone E

Free web search via DuckDuckGo. No API key required.
The DDGS client is synchronous, so calls run in a thread to avoid
blocking the event loop. Fail-open: returns [] on any error.
"""
from __future__ import annotations

import asyncio

try:
    from duckduckgo_search import DDGS
    SEARCH_OK = True
except ImportError:
    try:
        from ddgs import DDGS   # package was renamed in some versions
        SEARCH_OK = True
    except ImportError:
        DDGS = None             # type: ignore
        SEARCH_OK = False


def _search_sync(query: str, max_results: int) -> list[dict]:
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append({
                "title":   r.get("title", ""),
                "url":     r.get("href", "") or r.get("url", ""),
                "snippet": r.get("body", ""),
            })
    return results


async def web_search(query: str, max_results: int = 4) -> list[dict]:
    """
    Search the web and return [{title, url, snippet}, ...].
    Returns [] if duckduckgo_search isn't installed or the search fails.
    """
    if not SEARCH_OK:
        return []
    try:
        return await asyncio.to_thread(_search_sync, query, max_results)
    except Exception:
        return []
