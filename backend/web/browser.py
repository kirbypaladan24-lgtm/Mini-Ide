"""
web/browser.py — Mini IDE Milestone E

Fetches a web page's raw HTML. Capped timeout and response size so a
slow or huge page never stalls the chat pipeline.
"""
from __future__ import annotations

import httpx

_TIMEOUT    = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
_MAX_BYTES  = 800_000
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "Mini-IDE-Research-Agent/1.0"
)


async def fetch_page(url: str) -> str | None:
    """
    Fetch a page's HTML. Returns None on any error, non-200 status,
    or non-HTML content type.
    """
    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT, follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return None
            content_type = r.headers.get("content-type", "")
            if "text/html" not in content_type and "application/xhtml" not in content_type:
                return None
            return r.text[:_MAX_BYTES]
    except Exception:
        return None
