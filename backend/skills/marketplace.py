"""
skills/marketplace.py — Mini IDE Milestone B

Searches GitHub's code search API for .skill.yaml files.
No API key needed for public repositories (rate limit: 10 req/min unauthenticated).
"""
from __future__ import annotations

import httpx

_GITHUB_SEARCH = "https://api.github.com/search/code"
_TIMEOUT       = httpx.Timeout(10.0)


async def search_skills(query: str = "") -> list[dict]:
    """
    Return a list of skill metadata dicts from GitHub.
    Each dict has: name, description, repo, url, raw_url.
    Returns [] on any error (network, rate limit, etc.).
    """
    q = f"filename:.skill.yaml {query}".strip()
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get(
                _GITHUB_SEARCH,
                params={"q": q, "per_page": 20},
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            if r.status_code != 200:
                return []

            items = r.json().get("items", [])
            results = []
            for item in items:
                repo     = item["repository"]["full_name"]
                raw_base = f"https://raw.githubusercontent.com/{repo}/HEAD"
                results.append({
                    "name":     item["name"].replace(".skill.yaml", ""),
                    "repo":     repo,
                    "url":      item["html_url"],
                    "raw_url":  f"{raw_base}/{item['path']}",
                    "description": "",   # populated by installer after download
                })
            return results
    except Exception:
        return []
