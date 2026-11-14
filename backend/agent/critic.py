"""
agent/critic.py — Mini IDE Milestone A

Reviewer pipeline: after the coder generates code, a second model
reviews it for correctness, regressions, and alignment with the request.

Only fires for medium/complex tasks (risk=moderate|destructive from the
intent classifier). Simple tasks like docstrings skip this entirely.

Fail-open: if the critic errors for any reason, ok=True is returned
so the user's workflow is never hard-blocked.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from llm.client import stream_chat

# ── System prompt ─────────────────────────────────────────────────────────────
_CRITIC_SYSTEM = """\
You are a senior code reviewer embedded in a code editor called Mini IDE.

You will receive:
  1. The developer's original request
  2. The original file content
  3. The proposed new version

Your job is to check that the proposed change:
  ✓ Correctly fulfils the request
  ✓ Does not introduce bugs or break existing logic
  ✓ Does not remove code that wasn't asked to be removed
  ✓ Follows the existing coding style and conventions

Reply ONLY with valid JSON — no preamble, no explanation outside JSON:
{
  "ok": true,
  "issues": [],
  "suggestion": ""
}

Or if you find genuine problems:
{
  "ok": false,
  "issues": ["specific problem 1", "specific problem 2"],
  "suggestion": "one-sentence suggestion for the coder"
}

Rules:
- Approve (ok=true) for minor style differences — only reject real bugs
- Never reject because YOU would have written it differently
- Keep issues list short and actionable (max 3 items)
- If the original request is simple (add docstring, rename), approve by default
"""

_REVISE_SYSTEM = """\
You are an expert developer. A code reviewer has flagged issues with your
last implementation. Fix ONLY the specific issues listed.
Output the COMPLETE corrected file in a single fenced code block.
Do not truncate or omit any part of the file.
"""


# ── Public interface ──────────────────────────────────────────────────────────
async def review_code(
    original:  str,
    proposed:  str,
    request:   str,
    language:  str,
    model:     str = "qwen3:8b",
) -> dict:
    """
    Ask the critic model to review a proposed change.

    Returns:
        {"ok": bool, "issues": list[str], "suggestion": str}
    """
    ext = Path(f"f.{language}").suffix.lstrip(".") or language

    user_msg = (
        f"Developer request: {request}\n\n"
        f"Original file:\n```{ext}\n{original[:3_500]}\n```\n\n"
        f"Proposed change:\n```{ext}\n{proposed[:3_500]}\n```\n\n"
        "Review this. Reply with JSON only."
    )

    messages = [
        {"role": "system", "content": _CRITIC_SYSTEM},
        {"role": "user",   "content": user_msg},
    ]

    full = ""
    try:
        async for token in stream_chat(
            model, messages, temperature=0.05, num_ctx=2048
        ):
            full += token
            if len(full) > 800:   # critic response is short JSON — cap early
                break

        m = re.search(r"\{.*?\}", full, re.DOTALL)
        if m:
            data = json.loads(m.group())
            return {
                "ok":         bool(data.get("ok", True)),
                "issues":     [str(i) for i in data.get("issues", [])[:3]],
                "suggestion": str(data.get("suggestion", "")),
            }
    except Exception:
        pass

    return {"ok": True, "issues": [], "suggestion": ""}   # fail-open


async def coder_critic_loop(
    original:     str,
    proposed:     str,
    request:      str,
    language:     str,
    coder_model:  str,
    critic_model: str  = "qwen3:8b",
    max_cycles:   int  = 1,
    expand_context_fn = None,   # Milestone E: async (issues:list[str]) -> str | None
) -> tuple[str, dict]:
    """
    Run the coder → critic → optional-revise loop.

    Returns: (final_code: str, review: dict)
    The caller receives the best code the loop could produce.
    max_cycles=1 means: one revision attempt if the critic rejects.

    Milestone E: if expand_context_fn is provided, it's called once on the
    first rejection to fetch additional relevant context (e.g. extra RAG
    hits) which gets appended to the revision prompt — this is the
    "progressive context expansion" pattern: start narrow, widen only
    when the first attempt wasn't good enough.
    """
    current  = proposed
    last_rev = {"ok": True, "issues": [], "suggestion": ""}

    for cycle in range(max_cycles + 1):
        last_rev = await review_code(original, current, request, language, critic_model)

        if last_rev["ok"]:
            return current, last_rev

        if cycle >= max_cycles:
            # Hit the retry cap — return what we have and flag it
            return current, last_rev

        # Milestone E: widen context before asking for a revision
        extra_context = None
        if expand_context_fn is not None:
            try:
                extra_context = await expand_context_fn(last_rev["issues"])
            except Exception:
                extra_context = None

        # Ask the coder to revise
        revised = await _request_revision(
            original   = original,
            current    = current,
            request    = request,
            issues     = last_rev["issues"],
            suggestion = last_rev["suggestion"],
            language   = language,
            model      = coder_model,
            extra_context = extra_context,
        )
        if revised:
            current = revised
        else:
            break   # coder couldn't produce a revision → return current

    return current, last_rev


# ── Internal: ask the coder for a revision ───────────────────────────────────
async def _request_revision(
    original:   str,
    current:    str,
    request:    str,
    issues:     list[str],
    suggestion: str,
    language:   str,
    model:      str,
    extra_context: str | None = None,
) -> str | None:
    """Ask the coder to fix the specific issues raised by the critic."""
    ext = Path(f"f.{language}").suffix.lstrip(".") or language

    issues_str = "\n".join(f"  • {i}" for i in issues)
    hint       = f"Hint: {suggestion}\n\n" if suggestion else ""
    extra      = f"\nAdditional relevant context:\n{extra_context}\n" if extra_context else ""

    user_msg = (
        f"Original request: {request}\n\n"
        f"Issues with your implementation:\n{issues_str}\n\n"
        f"{hint}"
        f"Original file:\n```{ext}\n{original[:3_000]}\n```\n"
        f"{extra}\n"
        "Fix the issues listed. Output the complete corrected file."
    )

    messages = [
        {"role": "system", "content": _REVISE_SYSTEM},
        {"role": "user",   "content": user_msg},
    ]

    full = ""
    try:
        async for token in stream_chat(
            model, messages, temperature=0.1, num_ctx=4096
        ):
            full += token
    except Exception:
        return None

    m = re.search(r"```(?:\w+)?\n([\s\S]*?)```", full)
    return m.group(1) if m else None
