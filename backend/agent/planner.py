"""
agent/planner.py — Mini IDE Phase 5

Decomposes a natural-language task into an ordered list of concrete steps
using a small/fast LLM. Used by the orchestrator for multi-step tasks.

Phase 6 will use this to plan multi-file edits and call the patch engine.
"""
from __future__ import annotations

import json
import re

from llm.client import stream_chat
from llm.router import MODELS

_SYSTEM = (
    "You are a code editor agent planner. "
    "Given a developer task and optional workspace context, "
    "break the task into 3-7 concrete, ordered steps an AI agent can execute. "
    "Reply ONLY with a valid JSON array of step strings — no other text."
)


async def plan_task(
    task:            str,
    context_summary: str = "",
    model:           str = "",
) -> list[str]:
    """
    Return an ordered list of step strings for the given task.
    Falls back to [task] on any failure.
    """
    model   = model or MODELS.get("chat", "qwen3:8b")
    ctx_str = f"\n\nWorkspace context:\n{context_summary}" if context_summary else ""

    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",   "content": f"Task: {task}{ctx_str}"},
    ]

    full = ""
    try:
        async for token in stream_chat(model, messages, temperature=0.1, num_ctx=1024):
            full += token
            if len(full) > 2_000:
                break

        m = re.search(r"\[.*?\]", full, re.DOTALL)
        if m:
            steps = json.loads(m.group())
            if isinstance(steps, list) and steps:
                return [str(s).strip() for s in steps if s]
    except Exception:
        pass

    return [task]   # single-step fallback
