"""
agent/security_agent.py — Mini IDE Milestone D

Two-pass security analysis:
  1. Rule-based scan — fast, always runs, catches the obvious cases
  2. LLM second pass — only when the rule scan finds something ambiguous,
     asks a model whether it's a genuine risk in context

Fail-open: any error returns risk="low" with no findings rather than
blocking the user's workflow.
"""
from __future__ import annotations

import re

from llm.client import stream_chat

# ── Rule-based patterns ────────────────────────────────────────────────────────
_DANGEROUS_CALLS = [
    (re.compile(r"\bos\.system\s*\("),                "os.system() call — shell injection risk"),
    (re.compile(r"\beval\s*\("),                        "eval() — arbitrary code execution risk"),
    (re.compile(r"\bexec\s*\("),                        "exec() — arbitrary code execution risk"),
    (re.compile(r"subprocess\.\w+\([^)]*shell\s*=\s*True"), "subprocess with shell=True — injection risk"),
    (re.compile(r"\bpickle\.loads?\s*\("),               "pickle.load — unsafe deserialization risk"),
]

_DANGEROUS_PATTERNS = [
    (re.compile(r"rm\s+-rf\s+/"),                       "destructive shell command (rm -rf /)"),
    (re.compile(r"DROP\s+TABLE", re.IGNORECASE),         "DROP TABLE — destructive SQL"),
    (re.compile(r"DELETE\s+FROM\s+\w+\s*(;|$)", re.IGNORECASE | re.MULTILINE),
                                                          "DELETE FROM without WHERE clause"),
]

_PATH_TRAVERSAL = re.compile(r'["\'][^"\']*\.\./[^"\']*["\']')

_SECRET_PATTERNS = [
    (re.compile(r'(?i)(password|passwd|pwd)\s*=\s*["\'][^"\']{3,}["\']'), "hardcoded password"),
    (re.compile(r'(?i)(api[_-]?key)\s*=\s*["\'][^"\']{8,}["\']'),          "hardcoded API key"),
    (re.compile(r'(?i)(secret|token)\s*=\s*["\'][^"\']{8,}["\']'),         "hardcoded secret/token"),
]


def rule_scan(code: str) -> list[dict]:
    """Fast, always-on pattern scan. Returns a list of finding dicts."""
    findings = []

    for pattern, label in _DANGEROUS_CALLS:
        if pattern.search(code):
            findings.append({"severity": "high", "label": label})

    for pattern, label in _DANGEROUS_PATTERNS:
        if pattern.search(code):
            findings.append({"severity": "high", "label": label})

    if _PATH_TRAVERSAL.search(code):
        findings.append({"severity": "medium", "label": "possible path traversal (../)"})

    for pattern, label in _SECRET_PATTERNS:
        if pattern.search(code):
            findings.append({"severity": "medium", "label": label})

    return findings


async def llm_verify(
    code: str,
    findings: list[dict],
    model: str = "qwen3:8b",
) -> dict:
    """
    Ask the LLM to confirm whether the rule-scan findings are genuine risks
    in this specific context, or false positives (e.g. a hardcoded "secret"
    that's actually a test fixture).
    """
    if not findings:
        return {"confirmed": [], "dismissed": []}

    findings_str = "\n".join(f"- {f['label']}" for f in findings)
    messages = [
        {"role": "system", "content": (
            "You are a security reviewer. Given code and a list of automated "
            "findings, classify each as a genuine risk or a false positive "
            "(e.g. test fixtures, example/demo code, already-sanitized input). "
            "Reply ONLY with JSON: "
            '{"confirmed": ["finding text", ...], "dismissed": ["finding text", ...]}'
        )},
        {"role": "user", "content": f"Findings:\n{findings_str}\n\nCode:\n```\n{code[:3000]}\n```"},
    ]

    full = ""
    try:
        async for token in stream_chat(model, messages, temperature=0.0, num_ctx=2048):
            full += token
            if len(full) > 1000:
                break
        import json, re as _re
        m = _re.search(r"\{.*\}", full, _re.DOTALL)
        if m:
            data = json.loads(m.group())
            return {
                "confirmed": list(data.get("confirmed", [])),
                "dismissed": list(data.get("dismissed", [])),
            }
    except Exception:
        pass

    # Fail-open: treat all as confirmed if the LLM call fails (safer default)
    return {"confirmed": [f["label"] for f in findings], "dismissed": []}


async def analyze(
    code: str,
    model: str = "qwen3:8b",
    use_llm_pass: bool = True,
) -> dict:
    """
    Full security analysis. Returns:
      {"risk": "low"|"medium"|"high", "findings": [...], "summary": str}
    """
    findings = rule_scan(code)

    if not findings:
        return {"risk": "low", "findings": [], "summary": "No issues detected."}

    if use_llm_pass:
        verdict = await llm_verify(code, findings, model)
        confirmed_labels = set(verdict["confirmed"])
        findings = [f for f in findings if f["label"] in confirmed_labels] or findings

    if not findings:
        return {"risk": "low", "findings": [], "summary": "Automated findings were false positives."}

    highest = "high" if any(f["severity"] == "high" for f in findings) else "medium"
    summary = f"{len(findings)} issue(s) found: " + "; ".join(f["label"] for f in findings[:3])

    return {"risk": highest, "findings": findings, "summary": summary}
