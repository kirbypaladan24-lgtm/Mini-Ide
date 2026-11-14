"""
agent/workspace_planner.py — Mini IDE Sprint 3

The "thinking" step that runs before any code generation. Given the
user's request and a compressed map of the whole codebase, it outputs
a structured plan: which files need changing, why, and what the approach is.

If confidence is low it returns a clarifying question instead of a plan
so the user can narrow the request before code is generated.

Model: Qwen3 8B (the review model — same GPU slot, runs sequentially).
Output: structured JSON, parsed and returned as a Python dict.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from llm.client import stream_chat

_PLANNER_SYSTEM = """\
You are a senior software architect embedded in a code editor called Mini IDE.

You will receive:
  1. The developer's request
  2. A compact map of their entire codebase (file paths + function signatures)
  3. Relevant code snippets from semantic search (may be empty)

Your job is to produce a precise implementation plan in JSON.

Output ONLY valid JSON — no preamble, no markdown, no explanation outside the JSON.

Required format:
{
  "understanding": "one sentence: what the developer actually wants",
  "approach":      "one sentence: how you will implement it",
  "files_to_change": [
    {
      "file":      "relative/path/to/file.py",
      "reason":    "why this file needs to change",
      "changes":   "brief description of what will change",
      "risk":      "low | moderate | destructive",
      "edit_mode": "targeted | full_rewrite"
    }
  ],
  "files_to_read": ["paths of files to read for context but NOT change"],
  "confidence": 0.0,
  "clarifying_question": null
}

Rules:
- files_to_change must contain REAL paths that exist in the codebase map.
  Never invent paths.
- If the request is ambiguous OR confidence < 0.70, set clarifying_question
  to a short question and files_to_change to [].
- risk: "low" = adds new code, "moderate" = changes existing logic,
  "destructive" = deletes/rewrites significant existing code.
- edit_mode: "targeted" for a localized change to an EXISTING file (bug fix,
  add one function, rename something, tweak specific logic) — this is the
  default and should be used whenever possible, since it's faster and safer.
  Use "full_rewrite" ONLY for: a brand new file that doesn't exist yet, OR
  a request that explicitly asks to rewrite/refactor most of the file, OR
  changes so pervasive they'd touch the majority of the file's lines anyway.
- If the request is a plain question (no code change needed), return
  files_to_change: [] and confidence: 1.0.
- Keep files_to_read to the 1-3 most relevant context files only.
- Maximum 6 files in files_to_change.
"""


async def plan_changes(
    request:          str,
    codebase_summary: str,
    workspace:        Path,
    rag_context:      str = "",
    history:          list[dict] | None = None,
    model:            str = "qwen3:8b",
) -> dict:
    """
    Run the planner and return a plan dict.

    Returns a dict with keys:
      understanding, approach, files_to_change, files_to_read,
      confidence, clarifying_question

    Never raises — returns a safe fallback on any error.
    """
    rag_section = (
        f"\n\nRelevant code from semantic search:\n{rag_context}"
        if rag_context else ""
    )

    history_section = ""
    if history:
        recent = history[-4:]   # last 2 turns
        parts  = [f"{m['role'].upper()}: {m['content'][:200]}" for m in recent]
        history_section = "\n\nRecent conversation:\n" + "\n".join(parts)

    user_msg = (
        f"Developer request: {request}\n\n"
        f"Codebase map:\n{codebase_summary[:8_000]}"
        f"{rag_section}"
        f"{history_section}\n\n"
        f"Produce the JSON plan now."
    )

    messages = [
        {"role": "system", "content": _PLANNER_SYSTEM},
        {"role": "user",   "content": user_msg},
    ]

    full = ""
    try:
        async for token in stream_chat(model, messages, temperature=0.05, num_ctx=8192):
            full += token
            if len(full) > 4_000:
                break
    except Exception as e:
        return _fallback(f"Planner stream error: {e}")

    return _parse(full, workspace)


def _parse(raw: str, workspace: Path) -> dict:
    """Extract and validate the JSON plan from the model output."""
    # Strip markdown fences if the model wrapped the JSON
    text = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()

    # Find the JSON object
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return _fallback("Planner did not return JSON.")

    try:
        data = json.loads(m.group())
    except json.JSONDecodeError:
        return _fallback("Planner returned malformed JSON.")

    # Validate and clean files_to_change
    files_raw = data.get("files_to_change", [])
    files_clean: list[dict] = []
    for f in files_raw:
        if not isinstance(f, dict):
            continue
        file_path = str(f.get("file", "")).strip()
        if not file_path:
            continue
        # Normalize path separators
        file_path = file_path.replace("\\", "/")
        # Only include files that actually exist in the workspace
        abs_path = (workspace / file_path).resolve()
        if not abs_path.exists():
            # Try as a new file to create — keep it if it looks like a valid path
            if "/" in file_path or "." in file_path.split("/")[-1]:
                pass   # allow new files
            else:
                continue

        file_exists = abs_path.exists()

        # Safety: a file that doesn't exist yet has nothing to search/replace
        # against, so it must always be a full rewrite regardless of what
        # the planner said.
        edit_mode = str(f.get("edit_mode", "full_rewrite")).strip().lower()
        if edit_mode not in ("targeted", "full_rewrite"):
            edit_mode = "full_rewrite"
        if not file_exists:
            edit_mode = "full_rewrite"

        files_clean.append({
            "file":      file_path,
            "reason":    str(f.get("reason", "")),
            "changes":   str(f.get("changes", "")),
            "risk":      str(f.get("risk", "low")),
            "edit_mode": edit_mode,
        })

    return {
        "understanding":       str(data.get("understanding", "")),
        "approach":            str(data.get("approach", "")),
        "files_to_change":     files_clean,
        "files_to_read":       [str(p).replace("\\", "/") for p in data.get("files_to_read", [])],
        "confidence":          float(data.get("confidence", 0.8)),
        "clarifying_question": data.get("clarifying_question"),
    }


def _fallback(reason: str) -> dict:
    """Return a safe no-op plan when the planner fails."""
    return {
        "understanding":       "",
        "approach":            "",
        "files_to_change":     [],
        "files_to_read":       [],
        "confidence":          0.5,
        "clarifying_question": None,
        "_error":              reason,
    }


def is_pure_chat(request: str) -> bool:
    """
    Quick heuristic: is this clearly a question / explanation request
    that needs no file changes? Skip the planner entirely for these.
    """
    lower = request.lower().strip()
    question_starters = (
        "what ", "why ", "how ", "explain ", "describe ", "tell me",
        "what is", "what does", "can you explain", "show me how",
        "which ", "where is", "when did",
    )
    # If it ends with a question mark and starts with a question word, it's chat
    if lower.endswith("?") and any(lower.startswith(s) for s in question_starters):
        return True
    # "what does X do", "explain Y" patterns
    if re.match(r"^(what|why|how|explain|describe|tell|show)\b", lower):
        return True
    return False
