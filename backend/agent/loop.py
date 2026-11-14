"""
agent/loop.py — Mini IDE Phase 5, hardened in Milestone F

ReAct-style execution loop:
  Run → observe result → if error: generate fix → apply → retry

Implemented as an async generator so the caller (WebSocket handler)
can forward each event to the frontend in real time.

Milestone F additions:
  - Execution runs through tools.sandbox instead of a bare subprocess —
    restricted environment, no leaked secrets.
  - agent.diagnostics detects when the same error keeps repeating and
    switches model/strategy instead of blindly retrying the same way.
  - Generated fixes are scanned for hallucinated imports before being
    written to disk.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import AsyncGenerator

from llm.client  import stream_chat
from tools.sandbox import run_sandboxed
from tools.file_ops import write_file
from agent.diagnostics import (
    detect_loop, detect_hallucination, load_known_packages, suggest_alternate_model,
)

# ── System prompt for the fix model ──────────────────────────────────────────
_FIX_SYSTEM = (
    "You are an expert debugging assistant embedded in a code editor. "
    "The developer has run their code and it raised an error. "
    "Carefully read the file and the error, identify the root cause, then:\n"
    "  1. Write a brief explanation BEFORE the code block.\n"
    "  2. Output the COMPLETE corrected file in a SINGLE fenced code block.\n"
    "  3. Do NOT truncate or omit any part of the file.\n"
    "  4. Keep the original style and indentation.\n"
    "  5. Fix ONLY the error — do not change unrelated code."
)

_FIX_SYSTEM_RETHINK = (
    "You are an expert debugging assistant. Your PREVIOUS fix attempt for "
    "this error did not work — the exact same error happened again. "
    "Do NOT repeat the same fix. Think about this differently: consider "
    "whether the root cause might be somewhere else entirely (a different "
    "function, an import issue, a logic error upstream). "
    "Output the COMPLETE corrected file in a SINGLE fenced code block."
)

# ── Public entry point ────────────────────────────────────────────────────────
async def run_with_autofix(
    file_path:    str,
    language:     str,
    workspace:    Path,
    model:        str,
    max_attempts: int = 3,
    timeout:      int = 30,
) -> AsyncGenerator[dict, None]:
    """
    Async generator — yields WebSocket-ready event dicts.

    Usage in the WS handler:
        async for event in run_with_autofix(...):
            await websocket.send_json(event)
    """
    attempt_errors: list[str] = []
    known_packages = load_known_packages(workspace)
    current_model  = model

    for attempt in range(1, max_attempts + 1):

        # ── Run (Milestone F: sandboxed) ─────────────────────────────────────
        yield _step(attempt, "run",
                    f"Running `{file_path}` (attempt {attempt}/{max_attempts})…")

        result = await run_sandboxed(file_path, workspace, language, timeout)

        yield {
            "type":       "run_result",
            "stdout":     result["stdout"],
            "stderr":     result["stderr"],
            "returncode": result["returncode"],
            "success":    result["success"],
            "attempt":    attempt,
            "sandboxed":  result.get("sandboxed", "subprocess"),
        }

        if result["success"]:
            yield _done(True, f"✓ Completed successfully on attempt {attempt}.")
            return

        attempt_errors.append(result["stderr"])

        # ── Give up after final attempt ───────────────────────────────────────
        if attempt == max_attempts:
            yield _done(False,
                        f"✗ Still failing after {max_attempts} attempts.\n"
                        f"Last error: {result['stderr'][:400]}")
            return

        # ── Self-diagnosis (Milestone F): same error twice → change strategy ──
        is_looping = detect_loop(attempt_errors)
        fix_system = _FIX_SYSTEM

        if is_looping:
            alternate = suggest_alternate_model(current_model)
            yield {
                "type": "self_diagnosis",
                "message": (
                    f"Same error repeated — the fix isn't working. "
                    f"Switching strategy and trying {_short(alternate)} instead."
                ),
            }
            current_model = alternate
            fix_system = _FIX_SYSTEM_RETHINK

        # ── Generate fix ──────────────────────────────────────────────────────
        yield _step(attempt, "fix",
                    f"Error detected — asking {_short(current_model)} to generate a fix…")

        fixed = await _generate_fix(file_path, workspace, result, current_model, fix_system)

        if fixed is None:
            yield _done(False, "✗ Model did not return a code block — cannot apply fix.")
            return

        # ── Hallucination check (Milestone F) ────────────────────────────────
        if language == "python":
            suspicious = detect_hallucination(fixed, known_packages)
            if suspicious:
                yield {
                    "type": "self_diagnosis",
                    "message": (
                        f"⚠ The fix imports {', '.join(suspicious)} which aren't in "
                        f"requirements.txt — verify these packages actually exist "
                        f"before relying on this fix."
                    ),
                }

        # ── Apply fix ─────────────────────────────────────────────────────────
        try:
            abs_path = (workspace / file_path).resolve()
            write_file(abs_path, fixed)
        except Exception as e:
            yield _done(False, f"✗ Could not write fix: {e}")
            return

        yield {
            "type":    "agent_fix_applied",
            "attempt": attempt,
            "path":    file_path,
            "message": f"Fix applied — retrying ({attempt + 1}/{max_attempts})…",
        }


# ── Fix generation ────────────────────────────────────────────────────────────
async def _generate_fix(
    file_path: str,
    workspace: Path,
    result:    dict,
    model:     str,
    system_prompt: str = _FIX_SYSTEM,
) -> str | None:
    """Call the LLM to produce a fixed version of the file. Returns extracted code or None."""
    abs_path = (workspace / file_path).resolve()
    try:
        content = abs_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    ext = abs_path.suffix.lstrip(".") or "text"

    user_msg = (
        f"File `{file_path}`:\n```{ext}\n{content[:8_000]}\n```\n\n"
        f"Error output:\n```\n{result['stderr'][:2_000]}\n```"
    )
    if result["stdout"].strip():
        user_msg += f"\n\nStdout before crash:\n```\n{result['stdout'][:500]}\n```"
    user_msg += "\n\nPlease fix the error. Output the complete corrected file."

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_msg},
    ]

    full = ""
    try:
        async for token in stream_chat(model, messages, temperature=0.1, num_ctx=4096):
            full += token
    except Exception:
        return None

    return _extract_code(full)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _step(n: int, action: str, thought: str) -> dict:
    return {"type": "agent_step", "step": n, "action": action, "thought": thought}


def _done(success: bool, message: str) -> dict:
    return {"type": "agent_done", "success": success, "message": message}


def _extract_code(text: str) -> str | None:
    m = re.search(r"```(?:\w+)?\n([\s\S]*?)```", text)
    return m.group(1) if m else None


def _short(model: str) -> str:
    """Shorten a model name for display."""
    parts = model.split("/")[-1].split(":")
    return parts[0]
