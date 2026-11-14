"""
web/extractor.py — Mini IDE Milestone E

Strips a raw HTML page down to readable text, dropping nav/script/style
noise. Falls back to a naive regex strip if BeautifulSoup isn't installed.
"""
from __future__ import annotations

import re

try:
    from bs4 import BeautifulSoup
    BS4_OK = True
except ImportError:
    BeautifulSoup = None   # type: ignore
    BS4_OK = False

_STRIP_TAGS = {"script", "style", "nav", "footer", "header", "aside", "noscript"}


def extract_text(html: str, max_chars: int = 4_000) -> str:
    """Return clean, readable text from raw HTML, capped to max_chars."""
    if not html:
        return ""

    if BS4_OK:
        try:
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup.find_all(_STRIP_TAGS):
                tag.decompose()
            text = soup.get_text(separator="\n")
            return _clean_whitespace(text)[:max_chars]
        except Exception:
            pass

    # Fallback: naive tag stripping
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return _clean_whitespace(text)[:max_chars]


def _clean_whitespace(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)
