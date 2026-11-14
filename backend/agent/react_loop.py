"""
agent/react_loop.py — Mini IDE VS Code-style ReAct agent

Implements a Thought → Tool → Observation loop like VS Code's agent mode.
The LLM decides which tools to call; Python executes them and feeds results back.

Supports streaming thoughts and live tool execution via WebSocket.
Fail-operational: any parse/exec error returns observation and continues.

Max iterations: 14, max tokens per turn: 8k context.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from llm.client import stream_chat
from agent.react_tools import tool_definitions_prompt, dispatch_tool, TOOL_NAMES

_REACT_SYSTEM = """\
You are an autonomous coding agent embedded in Mini IDE — you work exactly like the agent in VS Code (Copilot / Cursor).

You have full tool access to the workspace. You MUST use tools to explore and act — never guess file contents or make edits blindly.

Available tools:
{tools}

WORKFLOW (follow strictly):
1. THINK step-by-step about the user's request and what you need to discover first.
2. CALL ONE TOOL PER TURN to gather information (read_file, grep, list_directory, etc.).
   Wait for the observation before calling the next tool.
3. After exploring, MAKE EDITS via write_file (create/overwrite). You may edit multiple files across multiple turns.
4. VERIFY your work by running tests/commands via run_command (e.g. `pytest -q`, `npm test`, `python -m py_compile file.py`).
   If tests fail, read the error, fix the code, and re-run — repeat until green or you have tried 2 fixes.
5. When done, provide a concise SUMMARY of what you changed and how you verified it.

OUTPUT FORMAT — you must output VALID JSON per turn, and NOTHING else outside the JSON:

For a tool call:
{{"thought": "one sentence: why this tool now", "tool": "read_file", "args": {{"path": "src/app.py"}}}}

For final answer (when all work is done and verified):
{{"thought": "final reasoning", "answer": "Summary with bullet points. Include file paths you changed and how you verified."}}

RULES:
- Output ONLY one JSON object per turn — no markdown, no extra text outside JSON.
- Always include "thought" — it is shown to the user as live reasoning.
- For write_file, "content" must be the COMPLETE new file content (not a diff). Read the file first so you don't truncate.
- Prefer surgical edits: read_file first, then write_file with minimal changes preserving style.
- After each write_file, consider running a verification command before proceeding to the next file.
- If you need line-specific context, use read_file_range after a grep hit.
- Never output a tool call and an answer in the same turn.
- If the user asks a pure question (no edit needed), answer directly with "answer" and no tool calls needed.
"""

# Loose JSON extraction (handles model wrapping in code fences)
_JSON_RE = re.compile(r"\{[\s\S]*\}", re.DOTALL)


def _extract_json(text: str) -> dict | None:
    """Extract first JSON object from text, handling fences and trailing chars."""
    # Strip fences
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    m = _JSON_RE.search(text)
    if not m:
        return None
    raw = m.group()
    # Try parse, with repair for trailing commas
    for attempt in [raw, re.sub(r",\s*}", "}", re.sub(r",\s*]", "]", raw))]:
        try:
            return json.loads(attempt)
        except json.JSONDecodeError:
            continue
    return None


async def _call_llm(model: str, messages: list[dict], num_ctx: int = 8192) -> str:
    """Single LLM call, returns full text."""
    full = ""
    try:
        async for token in stream_chat(model, messages, temperature=0.15, num_ctx=num_ctx):
            full += token
            if len(full) > 6000:  # cap per turn
                break
    except Exception as e:
        return json.dumps({"thought": f"LLM error: {e}", "answer": f"Error calling model: {e}"})
    return full


async def run_react_loop(
    websocket,
    request: str,
    workspace: Path,
    model: str = "qwen3:8b",
    history: list[dict] | None = None,
    codebase_summary: str = "",
    max_iterations: int = 14,
    language: str = "",
    file_path: str = "",
    file_content: str = "",
) -> dict:
    """
    Run the ReAct loop. Emits WebSocket events live.

    Events emitted:
      agent_thought {thought}
      tool_call {id, tool, args, thought}
      tool_result {id, tool, result, success}
      react_done {answer, iterations, files_changed}
    Returns summary dict for logging.
    """
    history = history or []
    # Build initial messages
    tool_prompt = tool_definitions_prompt()
    system_content = _REACT_SYSTEM.format(tools=tool_prompt)

    # Add workspace context as initial observation
    context_parts = []
    if codebase_summary:
        context_parts.append(f"Workspace overview (files + symbols):\n{codebase_summary[:6000]}")
    if file_path and file_content:
        ext = Path(file_path).suffix.lstrip(".") or "text"
        context_parts.append(f"Currently open file `{file_path}`:\n```{ext}\n{file_content[:5000]}\n```")
    if language:
        context_parts.append(f"Language: {language}")

    context_block = "\n\n".join(context_parts) if context_parts else "No workspace context yet — use list_directory to explore."

    messages: list[dict] = [
        {"role": "system", "content": system_content},
    ]
    # Inject workspace snapshot as synthetic exchange
    messages.append({"role": "user", "content": f"Workspace context:\n{context_block}"})
    messages.append({"role": "assistant", "content": json.dumps({"thought": "Context received. Ready for user request.", "answer": None})})

    # Append recent history (last 6 turns)
    for turn in history[-6:]:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": turn["content"][:2000]})

    # Current request
    messages.append({"role": "user", "content": request})

    files_changed: set[str] = set()
    iterations = 0

    await websocket.send_json({"type": "react_start", "message": "Agent started — thinking…", "model": model})

    for i in range(max_iterations):
        iterations = i + 1

        # Call LLM — show live thinking indicator (reviews, not chat message)
        await websocket.send_json({"type": "reviewing", "step": "react", "message": f"Thinking (step {iterations}/{max_iterations})…"})
        raw = await _call_llm(model, messages, num_ctx=8192)
        data = _extract_json(raw)

        if not data:
            # Fallback: treat raw as answer if no JSON
            # Try to salvage tool call via regex
            tool_match = re.search(r'"tool"\s*:\s*"(\w+)"', raw)
            if tool_match:
                # Malformed JSON — try to extract manually
                await websocket.send_json({"type": "agent_thought", "thought": f"Parse error — retrying. Raw: {raw[:200]}"})
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content": "Error: Your last output was not valid JSON. Re-output a single JSON object per the format."})
                continue
            # No tool, treat as final answer
            answer = raw.strip()
            if len(answer) > 20:
                await websocket.send_json({"type": "react_done", "answer": answer, "iterations": iterations, "files_changed": sorted(files_changed)})
                return {"answer": answer, "iterations": iterations, "files_changed": sorted(files_changed)}
            else:
                await websocket.send_json({"type": "agent_thought", "thought": f"Empty parse — retrying"})
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content": "Your output was empty or not JSON. Output a valid JSON object with thought+tool or thought+answer."})
                continue

        thought = data.get("thought", "")

        # Check for tool call
        tool_name = data.get("tool")
        answer = data.get("answer")

        if tool_name:
            # Validate tool
            if tool_name not in TOOL_NAMES:
                observation = f"Error: Unknown tool '{tool_name}'. Available: {', '.join(TOOL_NAMES)}"
                await websocket.send_json({"type": "tool_call", "id": iterations, "tool": tool_name, "args": data.get("args", {}), "thought": thought[:300]})
                await websocket.send_json({"type": "tool_result", "id": iterations, "tool": tool_name, "result": observation, "success": False})
                messages.append({"role": "assistant", "content": json.dumps(data)})
                messages.append({"role": "user", "content": f"Observation for {tool_name}: {observation}"})
                continue

            args = data.get("args", {}) or {}
            # Ensure args is dict
            if not isinstance(args, dict):
                args = {}

            await websocket.send_json({"type": "agent_thought", "thought": thought[:500] if thought else f"Using {tool_name}"})
            await websocket.send_json({"type": "tool_call", "id": iterations, "tool": tool_name, "args": args, "thought": thought[:300]})

            # Dispatch
            observation = await dispatch_tool(workspace, tool_name, args)
            success = not observation.startswith("Error:")

            # Track files changed
            if tool_name == "write_file" and success:
                files_changed.add(args.get("path", ""))

            # Truncate observation for context window but send full to frontend (truncated there too)
            obs_for_history = observation[:4000]
            await websocket.send_json({"type": "tool_result", "id": iterations, "tool": tool_name, "result": observation[:6000], "success": success})

            messages.append({"role": "assistant", "content": json.dumps(data)})
            messages.append({"role": "user", "content": f"Observation for {tool_name}:\n{obs_for_history}"})

            # Small delay to let frontend render
            continue

        elif answer is not None:
            # Final answer
            # If files were changed, append consistency note
            final_answer = str(answer).strip()
            if not final_answer:
                final_answer = thought or "Done."
            await websocket.send_json({"type": "react_done", "answer": final_answer, "iterations": iterations, "files_changed": sorted(files_changed)})
            return {"answer": final_answer, "iterations": iterations, "files_changed": sorted(files_changed)}

        else:
            # Neither tool nor answer — prompt to continue
            await websocket.send_json({"type": "agent_thought", "thought": thought[:500] if thought else "No tool or answer — asking to continue"})
            messages.append({"role": "assistant", "content": json.dumps(data)})
            messages.append({"role": "user", "content": "You must output either a tool call JSON or an answer JSON. Continue."})
            continue

    # Max iterations reached
    summary = f"Reached max iterations ({max_iterations}). Partial work on: {', '.join(sorted(files_changed)) or 'no files yet'}."
    await websocket.send_json({"type": "react_done", "answer": summary, "iterations": iterations, "files_changed": sorted(files_changed), "truncated": True})
    return {"answer": summary, "iterations": iterations, "files_changed": sorted(files_changed)}
