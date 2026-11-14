"""
tools/convention_detector.py — Mini IDE Sprint 2

Analyzes the most recently modified source files in the workspace to
extract the developer's coding conventions automatically. Result is
injected into every coder system prompt so the AI never writes code
in a different style.

Runs once when the workspace is set, then on demand. Fast enough to
run synchronously — pure AST + regex, no LLM call.
"""
from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path


_SKIP = frozenset({
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "dist", "build", ".next", ".uploads", ".rag_cache",
})

_MAX_FILES   = 10   # analyze the N most recently modified files
_MIN_LINES   = 15   # skip very short files (stubs, __init__.py, etc.)


# ── Entry point ───────────────────────────────────────────────────────────────
def detect_conventions(workspace: Path) -> dict:
    """
    Scan the workspace and return a conventions dict.
    Returns sensible defaults if too few files are found.
    """
    py_files = _recent_files(workspace, "*.py", _MAX_FILES)
    js_files = _recent_files(workspace, "*.jsx", _MAX_FILES // 2) + \
               _recent_files(workspace, "*.js",  _MAX_FILES // 2)

    conventions: dict = {
        "python": _python_conventions(py_files) if py_files else {},
        "javascript": _js_conventions(js_files) if js_files else {},
    }
    return conventions


def build_prompt_note(conventions: dict, language: str) -> str:
    """
    Return a one-paragraph convention note for injection into the
    coder system prompt. Empty string if nothing detected.
    """
    lang_key = "python" if language in ("python", "py") else \
               "javascript" if language in ("javascript", "jsx", "typescript", "tsx") else ""
    if not lang_key:
        return ""

    c = conventions.get(lang_key, {})
    if not c:
        return ""

    parts = []
    if lang_key == "python":
        if c.get("indent"):
            parts.append(c["indent"])
        if c.get("quotes"):
            parts.append(c["quotes"] + " quotes")
        if c.get("type_hints") is True:
            parts.append("always include type hints")
        elif c.get("type_hints") is False:
            parts.append("no type hints")
        if c.get("docstyle"):
            parts.append(c["docstyle"] + "-style docstrings")
        if c.get("async_first"):
            parts.append("prefer async functions")
        if c.get("dataclass"):
            parts.append("uses dataclasses")

    if lang_key == "javascript":
        if c.get("const_prefer"):
            parts.append("prefer const/let over var")
        if c.get("arrow_fn"):
            parts.append("prefer arrow functions")
        if c.get("semicolons") is False:
            parts.append("no semicolons")
        elif c.get("semicolons") is True:
            parts.append("always use semicolons")
        if c.get("single_quotes"):
            parts.append("single quotes")
        if c.get("trailing_comma"):
            parts.append("trailing commas")

    if not parts:
        return ""
    return "Convention note: this codebase uses " + ", ".join(parts) + "."


# ── Python analysis ───────────────────────────────────────────────────────────
def _python_conventions(files: list[Path]) -> dict:
    indent_votes:  Counter = Counter()
    quote_votes:   Counter = Counter()
    hint_votes:    Counter = Counter()
    doc_votes:     Counter = Counter()
    async_count    = 0
    sync_count     = 0
    dataclass_seen = False

    for path in files:
        try:
            src = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if src.count("\n") < _MIN_LINES:
            continue

        # Indentation: count leading spaces vs tabs on indented lines
        for line in src.splitlines():
            if line.startswith("    "):
                indent_votes["4-space"] += 1
            elif line.startswith("  ") and not line.startswith("   "):
                indent_votes["2-space"] += 1
            elif line.startswith("\t"):
                indent_votes["tab"] += 1

        # Quotes
        quote_votes["double"] += src.count('f"') + src.count('"')
        quote_votes["single"] += src.count("f'") + src.count("'")

        # Dataclasses
        if "@dataclass" in src:
            dataclass_seen = True

        # AST-based checks
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Type hints: check if returns annotation or arg annotations
                has_hints = bool(node.returns) or any(
                    a.annotation for a in node.args.args
                )
                hint_votes["yes" if has_hints else "no"] += 1

                # Async preference
                if isinstance(node, ast.AsyncFunctionDef):
                    async_count += 1
                else:
                    sync_count += 1

                # Docstring style
                first = ast.get_docstring(node)
                if first:
                    if "Args:" in first or "Returns:" in first:
                        doc_votes["Google"] += 1
                    elif "Parameters\n----------" in first:
                        doc_votes["NumPy"] += 1
                    else:
                        doc_votes["plain"] += 1

    result: dict = {}
    if indent_votes:
        result["indent"] = indent_votes.most_common(1)[0][0]
    if quote_votes:
        result["quotes"] = quote_votes.most_common(1)[0][0]
    if hint_votes:
        total = hint_votes["yes"] + hint_votes["no"]
        result["type_hints"] = (hint_votes["yes"] / total) > 0.6 if total else None
    if doc_votes:
        result["docstyle"] = doc_votes.most_common(1)[0][0]
    if async_count + sync_count > 0:
        result["async_first"] = async_count > sync_count
    result["dataclass"] = dataclass_seen

    return result


# ── JavaScript / JSX analysis ─────────────────────────────────────────────────
def _js_conventions(files: list[Path]) -> dict:
    const_count   = 0
    var_count     = 0
    arrow_count   = 0
    semi_count    = 0
    no_semi_count = 0
    sq_count      = 0
    dq_count      = 0
    trailing_comma = 0

    for path in files:
        try:
            src = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if src.count("\n") < _MIN_LINES:
            continue

        const_count    += len(re.findall(r"\b(const|let)\b", src))
        var_count      += len(re.findall(r"\bvar\b", src))
        arrow_count    += len(re.findall(r"=>\s*[{(]", src))
        sq_count       += src.count("'")
        dq_count       += src.count('"')
        trailing_comma += len(re.findall(r",\s*[}\]]", src))

        # Semicolons: check end-of-statement lines
        for line in src.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("//") and not stripped.startswith("*"):
                if stripped.endswith(";"):
                    semi_count += 1
                elif stripped[-1] in "abcdefghijklmnopqrstuvwxyz0123456789_'\")`]":
                    no_semi_count += 1

    result: dict = {}
    if const_count + var_count > 0:
        result["const_prefer"] = const_count > var_count
    if arrow_count > 5:
        result["arrow_fn"] = True
    if semi_count + no_semi_count > 10:
        result["semicolons"] = semi_count > no_semi_count
    result["single_quotes"] = sq_count > dq_count
    result["trailing_comma"] = trailing_comma > 5

    return result


# ── File helpers ──────────────────────────────────────────────────────────────
def _recent_files(workspace: Path, pattern: str, limit: int) -> list[Path]:
    files = []
    for p in workspace.rglob(pattern):
        if any(s in p.parts for s in _SKIP):
            continue
        try:
            files.append((p.stat().st_mtime, p))
        except Exception:
            continue
    files.sort(reverse=True)
    return [p for _, p in files[:limit]]
