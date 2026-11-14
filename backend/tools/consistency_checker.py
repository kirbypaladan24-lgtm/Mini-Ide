"""
tools/consistency_checker.py — Mini IDE Sprint 4

Runs after multi-file executor finishes to catch problems before
the user sees the diffs:

  1. Import validation — new imports that aren't in requirements.txt
  2. Caller consistency — changed function signatures whose callers
     weren't updated in this same plan

Returns warnings per file so the diff UI shows amber banners.
"""
from __future__ import annotations

from pathlib import Path

from agent.diagnostics import detect_hallucination, load_known_packages


def check_consistency(results: list[dict], workspace: Path) -> list[dict]:
    """
    Annotate each result dict with 'consistency_warnings: list[str]'.
    Fail-open on every check — never raises.
    """
    known_packages = load_known_packages(workspace)
    changed_files  = {r["file"] for r in results}

    for result in results:
        warnings: list[str] = []
        code      = result.get("code", "") or ""
        original  = result.get("original", "") or ""
        language  = result.get("language", "")

        # Check 1: hallucinated / missing Python imports
        if language == "python" and code:
            try:
                suspicious = detect_hallucination(code, known_packages)
                if suspicious:
                    warnings.append(
                        "Imports not in requirements.txt: "
                        + ", ".join(suspicious[:4])
                        + " — verify before applying."
                    )
            except Exception:
                pass

        # Check 2: changed signatures with callers not in the plan
        if language == "python" and code and original:
            try:
                from knowledge_graph.architecture import diff_changed_symbols
                from knowledge_graph.query        import find_callers
                changed = diff_changed_symbols(original, code, language)
                for sym in changed[:3]:
                    callers = find_callers(sym, workspace)
                    uncovered = [
                        c["file_path"] for c in callers
                        if c.get("file_path") and c["file_path"] not in changed_files
                    ]
                    if uncovered:
                        warnings.append(
                            f"'{sym}' changed but callers not in this plan: "
                            + ", ".join(uncovered[:3])
                        )
            except Exception:
                pass

        result["consistency_warnings"] = warnings

    return results


def summarize_warnings(results: list[dict]) -> str:
    total = sum(len(r.get("consistency_warnings", [])) for r in results)
    if total == 0:
        return ""
    return f"{total} consistency warning{'s' if total != 1 else ''} — review before applying."
