"""
tools/todo_scanner.py — Mini IDE Sprint 5

Scans every source file for TODO/FIXME/HACK/XXX comments and returns
them with surrounding context, ready for the "Resolve TODOs" workflow.
"""
from __future__ import annotations

import re
from pathlib import Path

_SKIP = frozenset({
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "dist", "build", ".next", ".uploads", ".rag_cache", ".checkpoints",
})

_SOURCE_EXTS = frozenset({".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".c", ".cpp", ".rs"})

_MARKERS = re.compile(
    r"(?:#|//|/\*)\s*(TODO|FIXME|HACK|XXX)\b[:\s]*(.*)",
    re.IGNORECASE,
)

_MAX_RESULTS = 100


def scan_todos(workspace: Path) -> list[dict]:
    """
    Walk the workspace and return every TODO/FIXME/HACK comment found.

    Each entry: {marker, text, file_path, line, context}
    context is the 2 lines before and after, for the AI to use when resolving.
    """
    results: list[dict] = []

    for path in workspace.rglob("*"):
        if len(results) >= _MAX_RESULTS:
            break
        if not path.is_file() or path.suffix.lower() not in _SOURCE_EXTS:
            continue
        if any(s in path.parts for s in _SKIP):
            continue

        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue

        rel = str(path.relative_to(workspace)).replace("\\", "/")

        for i, line in enumerate(lines):
            m = _MARKERS.search(line)
            if not m:
                continue
            marker = m.group(1).upper()
            text   = m.group(2).strip() or "(no description)"

            start = max(0, i - 2)
            end   = min(len(lines), i + 3)
            context = "\n".join(lines[start:end])

            results.append({
                "marker":    marker,
                "text":      text,
                "file_path": rel,
                "line":      i + 1,
                "context":   context,
            })

            if len(results) >= _MAX_RESULTS:
                break

    # Sort: FIXME/HACK first (more urgent), then by file
    priority = {"FIXME": 0, "HACK": 1, "XXX": 1, "TODO": 2}
    results.sort(key=lambda r: (priority.get(r["marker"], 3), r["file_path"], r["line"]))

    return results


def format_todo_summary(todos: list[dict]) -> str:
    if not todos:
        return "No TODOs found."
    by_marker: dict[str, int] = {}
    for t in todos:
        by_marker[t["marker"]] = by_marker.get(t["marker"], 0) + 1
    parts = [f"{v} {k}" for k, v in by_marker.items()]
    return f"Found {', '.join(parts)} across {len({t['file_path'] for t in todos})} file(s)."
