"""
agent/performance_agent.py — Mini IDE Milestone D

Detects common performance anti-patterns:
  - Nested loops (potential O(n²) or worse)
  - String/list concatenation inside loops
  - Repeated expensive calls inside loops (e.g. len() is fine, but
    re.compile() or DB queries inside a loop are not)
  - Redundant list/dict comprehension materialization

Rule-based first pass (fast, always available), LLM second pass for
deeper algorithmic analysis when the rule scan flags something.
"""
from __future__ import annotations

import re

from llm.client import stream_chat

# ── Rule-based heuristics ──────────────────────────────────────────────────────
_NESTED_LOOP = re.compile(
    r"for\s+\w+\s+in\s+.+:\s*\n(?:[ \t]+.*\n)*?[ \t]+for\s+\w+\s+in\s+.+:",
    re.MULTILINE,
)

_STRING_CONCAT_IN_LOOP = re.compile(
    r"for\s+\w+\s+in\s+.+:\s*\n(?:[ \t]+.*\n)*?[ \t]+\w+\s*\+=\s*[\"\']",
)

_LIST_APPEND_GROWTH = re.compile(
    r"for\s+\w+\s+in\s+.+:\s*\n(?:[ \t]+.*\n)*?[ \t]+\w+\s*=\s*\w+\s*\+\s*\[",
)

_QUERY_IN_LOOP = re.compile(
    r"for\s+\w+\s+in\s+.+:\s*\n(?:[ \t]+.*\n)*?[ \t]+"
    r"(execute|query|fetchall|fetchone|cursor\.)\w*\s*\(",
    re.IGNORECASE,
)

_REGEX_COMPILE_IN_LOOP = re.compile(
    r"for\s+\w+\s+in\s+.+:\s*\n(?:[ \t]+.*\n)*?[ \t]+re\.compile\s*\(",
)


def rule_scan(code: str) -> list[dict]:
    """Fast heuristic scan. Returns a list of finding dicts."""
    findings = []

    if _NESTED_LOOP.search(code):
        findings.append({
            "label": "Nested loop detected — verify this isn't O(n²) on large inputs",
            "severity": "medium",
        })
    if _STRING_CONCAT_IN_LOOP.search(code):
        findings.append({
            "label": "String concatenation (+=) inside a loop — use ''.join() instead",
            "severity": "low",
        })
    if _LIST_APPEND_GROWTH.search(code):
        findings.append({
            "label": "List rebuilt with + inside a loop — use .append() or a comprehension",
            "severity": "low",
        })
    if _QUERY_IN_LOOP.search(code):
        findings.append({
            "label": "Database query inside a loop — likely N+1 query problem",
            "severity": "high",
        })
    if _REGEX_COMPILE_IN_LOOP.search(code):
        findings.append({
            "label": "re.compile() inside a loop — move outside for reuse",
            "severity": "low",
        })

    return findings


async def llm_analyze(
    code: str,
    findings: list[dict],
    model: str = "qwen3:8b",
) -> str:
    """
    Ask the LLM for a one-paragraph performance assessment given the
    rule-based findings as a starting point. Returns a plain-text summary.
    """
    findings_str = "\n".join(f"- {f['label']}" for f in findings) if findings else "(none flagged by automated scan)"

    messages = [
        {"role": "system", "content": (
            "You are a performance reviewer. Briefly assess this code's "
            "time/space complexity and flag any genuine bottlenecks. "
            "Be concise — 2-3 sentences max. If the code is fine, say so."
        )},
        {"role": "user", "content": f"Automated findings:\n{findings_str}\n\nCode:\n```\n{code[:3000]}\n```"},
    ]

    full = ""
    try:
        async for token in stream_chat(model, messages, temperature=0.1, num_ctx=2048):
            full += token
            if len(full) > 600:
                break
    except Exception:
        return ""

    return full.strip()


async def analyze(
    code: str,
    model: str = "qwen3:8b",
    use_llm_pass: bool = True,
) -> dict:
    """
    Full performance analysis. Returns:
      {"findings": [...], "assessment": str}
    """
    findings = rule_scan(code)

    assessment = ""
    if use_llm_pass and findings:
        assessment = await llm_analyze(code, findings, model)

    return {"findings": findings, "assessment": assessment}
