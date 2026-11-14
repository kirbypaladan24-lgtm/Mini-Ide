"""
agent/router.py — Mini IDE Milestone D

Decides which specialist agents should run for a given task.
Keeps the pipeline fast: trivial tasks get zero specialists, only
genuinely risky or performance-sensitive tasks pay the extra latency.
"""
from __future__ import annotations

import re

# ── Keyword triggers ──────────────────────────────────────────────────────────
_PERF_KEYWORDS = re.compile(
    r"\b(optimi[sz]e|performance|slow|faster|speed up|efficient|bottleneck)\b",
    re.IGNORECASE,
)
_SECURITY_KEYWORDS = re.compile(
    r"\b(security|vulnerab|injection|sanitiz|auth|password|secret|token|encrypt)\b",
    re.IGNORECASE,
)

# Patterns in the FILE CONTENT (not the request) that imply security sensitivity
_SENSITIVE_FILE_PATTERNS = re.compile(
    r"\b(password|api_key|secret|token|subprocess|os\.system|eval\(|exec\(|"
    r"DROP TABLE|DELETE FROM|sql|query|auth|login|session)\b",
    re.IGNORECASE,
)


def route(
    request:      str,
    file_content: str,
    risk:         str,        # from the intent classifier: safe|moderate|destructive
    language:     str,
) -> list[str]:
    """
    Return an ordered list of specialist agent names to run.
    Possible values: "verify", "critic", "security", "performance"

    "verify" always runs (cheap, local, no LLM call).
    "critic" runs for moderate/destructive risk.
    "security"/"performance" run only when triggered by keywords or content.
    """
    agents = ["verify"]

    if risk in ("moderate", "destructive"):
        agents.append("critic")

    if _SECURITY_KEYWORDS.search(request) or _SENSITIVE_FILE_PATTERNS.search(file_content[:5000]):
        agents.append("security")

    if _PERF_KEYWORDS.search(request):
        agents.append("performance")

    return agents


def estimate_duration(agents: list[str]) -> str:
    """Rough human-readable time estimate for the selected pipeline."""
    seconds = 0
    weights = {"verify": 1, "critic": 8, "security": 6, "performance": 6}
    for a in agents:
        seconds += weights.get(a, 4)
    if seconds <= 2:
        return "a few seconds"
    if seconds <= 10:
        return "~10 seconds"
    if seconds <= 20:
        return "~20 seconds"
    return "~30+ seconds"
