"""
agent/multi_file_executor.py — Mini IDE Sprint 3, hardened with
VS Code-agent-style surgical edits

Orchestrates code generation for every file in the planner's output.
Files are processed sequentially (one at a time) since the RTX 4050
only runs one model at a time.

Two edit modes, chosen per-file by the planner:
  "targeted"     - ask for SEARCH/REPLACE blocks, apply them mechanically.
                   Faster, cheaper, and the model can't accidentally drop
                   unrelated code since it never re-types the whole file.
  "full_rewrite" - the model writes the complete file. Used for new files
                   or genuinely sweeping changes.

If targeted mode fails (model didn't produce valid/applicable blocks),
this automatically falls back to a full-rewrite attempt rather than
giving up - the person should never see "editing failed" for something
recoverable.

WebSocket events emitted per file:
  {"type": "file_start",  "file", "index", "total", "reason"}
  {"type": "token",       "content"}                              (streaming)
  {"type": "agent_turn",  "agent", "file", "summary", "content"}  (transparency)
  {"type": "reviewing",   "step", "message"}
  {"type": "file_done",   "file", "index", "total", "success", "review"}
"""
from __future__ import annotations

import re
from pathlib import Path

from llm.client      import stream_chat
from tools.verifier  import run_pipeline as verify_code
from tools.file_ops  import read_file
from agent.router    import route as route_agents
from agent.critic    import coder_critic_loop
from agent.trust     import compute_trust_score
from agent import security_agent, performance_agent
from agent.surgical_editor import (
    parse_edit_blocks, apply_edit_blocks, has_valid_blocks,
    strip_blocks_for_display, summarize_blocks,
)

_FULL_REWRITE_SYSTEM = """\
You are an expert AI code editor embedded in Mini IDE.

You are making a full rewrite of ONE file as part of a larger multi-file plan.
The plan context tells you what other files are changing simultaneously so you can
keep everything consistent.

Rules:
1. Output the COMPLETE updated file in a SINGLE fenced code block - no truncation.
2. Put a brief one-sentence explanation BEFORE the code block.
3. Make ONLY the changes described. Do not refactor unrelated code.
4. Match the existing file's style, indentation, and conventions exactly.
5. If creating a new file, write the complete initial implementation.

FORMAT EXAMPLE:
Here is the updated file with the rate limiter added.

```python
# ... complete file content ...
```

CRITICAL: always close the code block with ``` on its own line.
"""

_SURGICAL_SYSTEM = """\
You are an expert AI code editor embedded in Mini IDE, making a TARGETED
change to one file - like a senior engineer using precise find-and-replace,
not rewriting the whole file.

Output ONE OR MORE edit blocks in this EXACT format:

<<<<<<< SEARCH
[the exact existing code to find - copy it character for character,
including all whitespace and indentation]
=======
[the new code that replaces it]
>>>>>>> REPLACE

Rules:
1. The SEARCH text must match the file shown to you EXACTLY - copy it verbatim,
   including indentation. Do not paraphrase or reformat it.
2. Keep each SEARCH block as SHORT as possible while still being unique in
   the file - a few lines of surrounding context, not the whole function
   unless the whole function is changing.
3. Use multiple separate blocks if you're changing multiple distinct locations
   in the file.
4. Write a brief one-sentence explanation BEFORE the blocks.
5. Do NOT wrap the blocks in triple-backtick code fences.
6. Never include line numbers inside the blocks - only real code.
"""


async def execute_plan(
    websocket,
    plan:          dict,
    request:       str,
    workspace:     Path,
    coder_model:   str,
    review_model:  str = "qwen3:8b",
) -> list[dict]:
    """
    Execute a workspace plan. Sends WebSocket events for each file.
    Returns a list of result dicts (one per file):
      {"file", "code", "original", "language", "review", "success", "edit_mode_used"}
    """
    files_to_change = plan.get("files_to_change", [])
    total           = len(files_to_change)
    results: list[dict] = []

    read_context = _load_read_files(plan.get("files_to_read", []), workspace)

    for index, file_entry in enumerate(files_to_change, 1):
        file_path = file_entry["file"]
        reason    = file_entry.get("reason", "")
        changes   = file_entry.get("changes", "")
        risk      = file_entry.get("risk", "low")
        edit_mode = file_entry.get("edit_mode", "full_rewrite")

        await websocket.send_json({
            "type":  "file_start",
            "file":  file_path,
            "index": index,
            "total": total,
            "reason": reason,
            "edit_mode": edit_mode,
        })

        abs_path = (workspace / file_path).resolve()
        try:
            original, language = read_file(abs_path) if abs_path.exists() else ("", _detect_lang(file_path))
        except Exception:
            original = ""
            language = _detect_lang(file_path)

        gen = await _generate_file(
            websocket    = websocket,
            file_path    = file_path,
            original     = original,
            language     = language,
            request      = request,
            reason       = reason,
            changes      = changes,
            plan         = plan,
            read_context = read_context,
            model        = coder_model,
            edit_mode    = edit_mode,
        )
        code = gen["code"]

        await websocket.send_json({
            "type":    "agent_turn",
            "agent":   "coder",
            "file":    file_path,
            "summary": gen["turn_summary"],
            "content": gen["turn_content"],
        })

        review = {"ok": True, "verified": False, "issues": [], "warnings": [],
                  "agents_run": ["verify"], "security": None, "performance": None,
                  "edit_mode_used": gen["edit_mode_used"]}
        if code and language in ("python", "javascript", "typescript"):
            v = verify_code(code, language)
            review["verified"] = v.ok
            review["warnings"] = v.warnings
            if not v.ok:
                review["ok"]     = False
                review["issues"] = v.errors

        if code and review["ok"] and language in ("python", "javascript", "typescript"):
            agents = route_agents(request, code, risk, language)
            review["agents_run"] = agents

            if "critic" in agents and original:
                await websocket.send_json({
                    "type": "reviewing", "step": "critic",
                    "message": f"Reviewing {file_path} with critic model...",
                })
                code, crit = await coder_critic_loop(
                    original=original, proposed=code, request=request,
                    language=language, coder_model=coder_model,
                    critic_model=review_model, max_cycles=1,
                )
                review["issues"] = crit.get("issues", [])
                if not crit["ok"]:
                    review["ok"] = False
                await websocket.send_json({
                    "type":    "agent_turn",
                    "agent":   "critic",
                    "file":    file_path,
                    "summary": "Approved" if crit["ok"] else f"{len(crit.get('issues', []))} issue(s) found",
                    "content": "\n".join(f"- {i}" for i in crit.get("issues", [])) or "No issues found.",
                })

            if "security" in agents:
                await websocket.send_json({
                    "type": "reviewing", "step": "security",
                    "message": f"Scanning {file_path} for security issues...",
                })
                sec = await security_agent.analyze(code, model=review_model)
                review["security"] = sec
                if sec["risk"] == "high":
                    review["ok"] = False
                await websocket.send_json({
                    "type":    "agent_turn",
                    "agent":   "security",
                    "file":    file_path,
                    "summary": f"Risk: {sec['risk']}" + (f" - {len(sec['findings'])} finding(s)" if sec["findings"] else ""),
                    "content": sec.get("summary", "No issues detected."),
                })

            if "performance" in agents:
                await websocket.send_json({
                    "type": "reviewing", "step": "performance",
                    "message": f"Checking {file_path} for performance issues...",
                })
                perf = await performance_agent.analyze(code, model=review_model)
                review["performance"] = perf
                findings = perf.get("findings", [])
                await websocket.send_json({
                    "type":    "agent_turn",
                    "agent":   "performance",
                    "file":    file_path,
                    "summary": f"{len(findings)} finding(s)" if findings else "No issues found",
                    "content": perf.get("assessment") or "\n".join(f"- {f['label']}" for f in findings) or "No issues found.",
                })

        review["trust"] = compute_trust_score(review)

        results.append({
            "file":     file_path,
            "code":     code or "",
            "original": original,
            "language": language,
            "review":   review,
            "success":  bool(code),
            "edit_mode_used": gen["edit_mode_used"],
        })

        await websocket.send_json({
            "type":    "file_done",
            "file":    file_path,
            "index":   index,
            "total":   total,
            "success": bool(code),
            "review":  review,
        })

    return results


async def _generate_file(
    websocket,
    file_path:    str,
    original:     str,
    language:     str,
    request:      str,
    reason:       str,
    changes:      str,
    plan:         dict,
    read_context: str,
    model:        str,
    edit_mode:    str,
) -> dict:
    """
    Generate the new content for a single file.

    Returns:
      {"code": str|None, "edit_mode_used": str,
       "turn_summary": str, "turn_content": str}
    """
    is_new_file = not bool(original)

    if edit_mode == "targeted" and not is_new_file:
        result = await _generate_targeted(
            websocket, file_path, original, language, request, reason, changes,
            plan, read_context, model,
        )
        if result["code"] is not None:
            return result
        # Targeted mode failed to produce an applicable edit - fall back
        # to a full rewrite rather than surfacing a dead end to the user.

    return await _generate_full_rewrite(
        websocket, file_path, original, language, request, reason, changes,
        plan, read_context, model, is_new_file,
    )


async def _generate_targeted(
    websocket, file_path, original, language, request, reason, changes,
    plan, read_context, model,
) -> dict:
    """Attempt a surgical SEARCH/REPLACE edit. code=None signals fallback needed."""
    ext          = _ext(language)
    plan_summary = _build_plan_summary(plan, exclude=file_path)
    original_clipped = original[:8_000]
    clip_note = "\n\n... (file truncated to 8000 chars for context)" if len(original) > 8_000 else ""

    user_msg = (
        f"OVERALL REQUEST: {request}\n\n"
        f"YOUR TASK - edit {file_path}\n"
        f"Reason: {reason}\n"
        f"What to change: {changes}\n\n"
        + (f"OTHER FILES BEING CHANGED IN THIS PLAN:\n{plan_summary}\n\n" if plan_summary else "")
        + (f"RELATED CONTEXT (read-only):\n{read_context[:2_000]}\n\n" if read_context else "")
        + f"CURRENT FILE CONTENT ({file_path}):\n```{ext}\n{original_clipped}{clip_note}\n```\n\n"
        + "Output your SEARCH/REPLACE block(s) now."
    )

    messages = [
        {"role": "system", "content": _SURGICAL_SYSTEM},
        {"role": "user",   "content": user_msg},
    ]

    full = ""
    try:
        async for token in stream_chat(model, messages, temperature=0.1, num_ctx=8192):
            full += token
            await websocket.send_json({"type": "token", "content": token})
    except Exception as e:
        return {"code": None, "edit_mode_used": "targeted",
                "turn_summary": "Generation failed", "turn_content": str(e)}

    if not has_valid_blocks(full):
        return {"code": None, "edit_mode_used": "targeted",
                "turn_summary": "No valid edit blocks - falling back to full rewrite",
                "turn_content": full[:500]}

    blocks       = parse_edit_blocks(full)
    apply_result = apply_edit_blocks(original, blocks)
    explanation  = strip_blocks_for_display(full)

    if apply_result["applied"] == 0:
        reasons = "; ".join(f["reason"] for f in apply_result["failed"])
        return {"code": None, "edit_mode_used": "targeted",
                "turn_summary": "Could not locate edit targets - falling back to full rewrite",
                "turn_content": f"{explanation}\n\nFailed: {reasons}"}

    turn_summary = summarize_blocks(blocks)
    if apply_result["failed"]:
        turn_summary += f" ({len(apply_result['failed'])} block(s) skipped)"

    turn_content = explanation or "(no explanation given)"
    if apply_result["failed"]:
        turn_content += "\n\nSome edits could not be applied:\n" + "\n".join(
            f"- {f['reason']}: {f['search'][:100]}" for f in apply_result["failed"]
        )

    return {
        "code": apply_result["content"],
        "edit_mode_used": "targeted",
        "turn_summary": turn_summary,
        "turn_content": turn_content,
    }


async def _generate_full_rewrite(
    websocket, file_path, original, language, request, reason, changes,
    plan, read_context, model, is_new_file,
) -> dict:
    """Full-file generation - the proven, always-available path."""
    ext = _ext(language)
    plan_summary = _build_plan_summary(plan, exclude=file_path)
    original_clipped = original[:6_000]
    clip_note = "\n\n... (file truncated to 6000 chars for context)" if len(original) > 6_000 else ""

    if is_new_file:
        action = f"Create this new file: {file_path}\nPurpose: {reason}\nContent to implement: {changes}"
    else:
        action = (
            f"Edit this file: {file_path}\n"
            f"Reason for change: {reason}\n"
            f"What to change: {changes}"
        )

    user_msg = (
        f"OVERALL REQUEST: {request}\n\n"
        f"YOUR TASK: {action}\n\n"
        + (f"OTHER FILES BEING CHANGED IN THIS PLAN:\n{plan_summary}\n\n" if plan_summary else "")
        + (f"RELATED CONTEXT (read-only):\n{read_context[:2_000]}\n\n" if read_context else "")
        + (f"CURRENT FILE CONTENT:\n```{ext}\n{original_clipped}{clip_note}\n```\n\n" if not is_new_file else "")
        + "Generate the complete file now."
    )

    messages = [
        {"role": "system", "content": _FULL_REWRITE_SYSTEM},
        {"role": "user",   "content": user_msg},
    ]

    full = ""
    try:
        async for token in stream_chat(model, messages, temperature=0.1, num_ctx=8192):
            full += token
            await websocket.send_json({"type": "token", "content": token})
    except Exception as e:
        return {"code": None, "edit_mode_used": "full_rewrite",
                "turn_summary": "Generation failed", "turn_content": str(e)}

    code = _extract_code(full)
    explanation = re.sub(r"```(?:\w+)?\n[\s\S]*?```", "", full).strip()

    return {
        "code": code,
        "edit_mode_used": "full_rewrite",
        "turn_summary": "New file created" if is_new_file else "Full file rewrite",
        "turn_content": explanation or "(no explanation given)",
    }


def _extract_code(text: str) -> str | None:
    """Extract the fenced code block. Falls back to unterminated fences."""
    m = re.search(r"```(?:\w+)?\n([\s\S]*?)```", text)
    if m:
        return m.group(1)
    m2 = re.search(r"```(?:\w+)?\n([\s\S]+)$", text)
    if m2 and len(m2.group(1).strip()) > 20:
        return m2.group(1)
    return None


def _load_read_files(paths: list[str], workspace: Path) -> str:
    parts = []
    for rel in paths[:3]:
        abs_p = (workspace / rel).resolve()
        if abs_p.exists():
            try:
                content, _ = read_file(abs_p)
                parts.append(f"[{rel}]\n{content[:1_500]}")
            except Exception:
                pass
    return "\n\n".join(parts)


def _build_plan_summary(plan: dict, exclude: str) -> str:
    lines = []
    for f in plan.get("files_to_change", []):
        if f["file"] != exclude:
            lines.append(f"  - {f['file']}: {f['changes']}")
    return "\n".join(lines)


def _detect_lang(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    return {
        ".py": "python", ".js": "javascript", ".jsx": "javascript",
        ".ts": "typescript", ".tsx": "typescript", ".sh": "bash",
        ".sql": "sql", ".md": "markdown", ".yaml": "yaml", ".yml": "yaml",
    }.get(ext, "text")


def _ext(language: str) -> str:
    return {
        "python": "python", "javascript": "javascript",
        "typescript": "typescript", "bash": "bash",
        "sql": "sql", "markdown": "md",
    }.get(language, language)
