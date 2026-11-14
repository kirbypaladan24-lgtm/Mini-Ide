"""
agent/pipeline.py — Mini IDE Milestone D

Orchestrates the full quality pipeline for AI-generated code edits.
Replaces the inline _quality_pipeline from Milestone A with a
router-driven, journaled version that adds security and performance
specialists only when relevant.

Sequence (specialists chosen by agent.router.route):
  verify (always) → [autofix if needed] → critic → security → performance

Every step is timed and recorded to the agent journal regardless of
outcome, so the Agent Log always reflects what actually happened.
"""
from __future__ import annotations

import re

from llm.client import stream_chat
from tools.verifier import run_pipeline as verify_code
from agent.critic import coder_critic_loop
from agent.router import route as route_agents, estimate_duration
from agent.journal import TaskJournal
from agent.trust   import compute_trust_score
from agent import security_agent, performance_agent


async def run_pipeline(
    websocket,
    code:         str,
    language:     str,
    request:      str,
    original:     str,
    coder_model:  str,
    risk:         str = "safe",
    file_path:    str = "",
    review_model: str = "qwen3:8b",
) -> tuple[str, dict]:
    """
    Run the full agent pipeline. Sends progress events over the websocket
    as each specialist runs. Returns (final_code, review_summary).

    review_summary includes: ok, verified, issues, warnings, revised,
    security, performance, agents_run, journal_id
    """
    journal = TaskJournal(request=request, file_path=file_path)
    final_code = code
    review: dict = {
        "ok": True, "verified": False, "issues": [], "warnings": [],
        "revised": False, "security": None, "performance": None,
    }

    agents = route_agents(request, original, risk, language)
    await websocket.send_json({
        "type":     "pipeline_plan",
        "agents":   agents,
        "estimate": estimate_duration(agents),
    })

    # ── Step: verify ──────────────────────────────────────────────────────────
    with journal.step("verify", reason="always runs — syntax/AST/lint check") as step:
        await websocket.send_json({
            "type": "reviewing", "step": "verify", "message": "Verifying syntax…",
        })
        v = verify_code(code, language)
        review["verified"] = v.ok
        review["warnings"] = v.warnings
        step.note(f"ok={v.ok} step={v.step}")
        if not v.ok:
            step.finding(f"{v.step} error: {'; '.join(v.errors[:2])}")

        if not v.ok:
            await websocket.send_json({
                "type": "reviewing", "step": "fix",
                "message": f"Syntax issue — auto-fixing ({v.step})…",
            })
            with journal.step("autofix", reason=f"{v.step} failed verification", model=coder_model) as fixstep:
                for _ in range(2):
                    candidate = await _request_syntax_fix(final_code, v.errors, language, coder_model)
                    if candidate is None:
                        break
                    v2 = verify_code(candidate, language)
                    if v2.ok:
                        final_code = candidate
                        review["verified"] = True
                        review["revised"]  = True
                        fixstep.note("fixed on retry")
                        break
                else:
                    fixstep.note("auto-fix exhausted, returning best effort")

    # ── Step: critic ──────────────────────────────────────────────────────────
    if "critic" in agents and original:
        await websocket.send_json({
            "type": "reviewing", "step": "critic", "message": "Reviewing with critic model…",
        })
        with journal.step("critic", reason="risk=moderate/destructive", model=review_model) as step:

            # Milestone E: progressive context expansion — widen RAG context
            # only if the critic rejects the first attempt
            async def _expand_context(issues: list[str]) -> str | None:
                try:
                    from rag.retriever import semantic_search, format_rag_context
                    query = " ".join(issues)[:300] or request
                    hits = await semantic_search(query, k=5, exclude_paths={file_path})
                    if hits:
                        step.note(f"expanded context with {len(hits)} extra RAG hits")
                        return format_rag_context(hits)
                except Exception:
                    pass
                return None

            final_code, crit = await coder_critic_loop(
                original=original, proposed=final_code, request=request,
                language=language, coder_model=coder_model,
                critic_model=review_model, max_cycles=1,
                expand_context_fn=_expand_context,
            )
            review["issues"]  = crit.get("issues", [])
            review["revised"] = review["revised"] or (final_code != code)
            if not crit["ok"]:
                review["ok"] = False
                for issue in crit.get("issues", []):
                    step.finding(issue)
            else:
                step.note("approved")

    # ── Step: security ───────────────────────────────────────────────────────
    if "security" in agents:
        await websocket.send_json({
            "type": "reviewing", "step": "security", "message": "Scanning for security issues…",
        })
        with journal.step("security", reason="security-sensitive content detected", model=review_model) as step:
            sec = await security_agent.analyze(final_code, model=review_model)
            review["security"] = sec
            step.note(f"risk={sec['risk']}")
            for f in sec.get("findings", []):
                step.finding(f["label"])
            if sec["risk"] == "high":
                review["ok"] = False

    # ── Step: performance ─────────────────────────────────────────────────────
    if "performance" in agents:
        await websocket.send_json({
            "type": "reviewing", "step": "performance", "message": "Checking performance…",
        })
        with journal.step("performance", reason="optimization request detected", model=review_model) as step:
            perf = await performance_agent.analyze(final_code, model=review_model)
            review["performance"] = perf
            for f in perf.get("findings", []):
                step.finding(f["label"])
            if perf.get("assessment"):
                step.note(perf["assessment"][:200])

    review["agents_run"] = agents
    review["journal_id"] = journal.id
    review["trust"]      = compute_trust_score(review)   # Milestone G
    journal.finish(outcome="applied" if review["ok"] else "flagged")

    return final_code, review


# ── Helper: syntax auto-fix request ───────────────────────────────────────────
async def _request_syntax_fix(
    code: str, errors: list[str], language: str, model: str,
) -> str | None:
    ext  = language[:2]
    msgs = [
        {"role": "system",
         "content": "Fix the syntax error in this code. Output ONLY the corrected "
                    "file in a single fenced code block, nothing else."},
        {"role": "user",
         "content": "Error: " + "; ".join(errors) + "\n\n```" + ext + "\n" + code + "\n```"},
    ]
    buf = ""
    try:
        async for tok in stream_chat(model, msgs, temperature=0.0, num_ctx=4096):
            buf += tok
    except Exception:
        return None
    m = re.search(r"```(?:\w+)?\n([\s\S]*?)```", buf)
    return m.group(1) if m else None
