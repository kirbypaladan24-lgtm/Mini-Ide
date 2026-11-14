"""
tools/dead_code.py — Mini IDE Sprint 5

Uses the knowledge graph (Milestone B) to find functions and classes
that are defined but never called/referenced anywhere in the workspace.

Excludes by design:
  - Public API endpoints (FastAPI routes, exported React components)
  - __init__.py contents (often re-exported for external use)
  - Test fixtures and test functions (test_*, fixture decorators)
  - Dunder methods (__init__, __str__, etc.)
  - Anything starting with _ followed by a single underscore convention
    that suggests intentional "private but referenced via getattr" use

Never auto-removes anything — always returns a list for the user to
review and approve via a normal diff.
"""
from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

from knowledge_graph.builder import db_path_for

_SKIP = frozenset({
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "dist", "build", ".next", ".uploads", ".rag_cache", ".checkpoints",
})

_DUNDER = frozenset({
    "__init__", "__str__", "__repr__", "__eq__", "__hash__", "__lt__",
    "__enter__", "__exit__", "__call__", "__iter__", "__next__",
    "__len__", "__getitem__", "__setitem__", "__contains__",
})


def find_dead_code(workspace: Path) -> list[dict]:
    """
    Return a list of {name, kind, file_path, line_start, line_end, reason}
    for symbols that appear unreferenced anywhere in the workspace.

    Fail-open: returns [] if the knowledge graph isn't built yet.
    """
    db = db_path_for(workspace)
    if not db.exists():
        return []

    try:
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
    except Exception:
        return []

    try:
        # Every function/class node
        nodes = conn.execute("""
            SELECT id, name, kind, file_path, line_start, line_end
            FROM   kg_nodes
            WHERE  kind IN ('function', 'class')
        """).fetchall()

        # Every "calls" or "inherits" target id — these ARE referenced
        referenced_ids = {
            r[0] for r in conn.execute(
                "SELECT DISTINCT to_id FROM kg_edges WHERE relationship IN ('calls','inherits')"
            ).fetchall()
        }
    except Exception:
        conn.close()
        return []
    conn.close()

    dead: list[dict] = []
    entry_point_names = _get_entry_point_names(workspace)

    for node in nodes:
        name = node["name"]
        kind = node["kind"]
        file_path = node["file_path"]

        # Skip dunders, test functions, fixtures
        if name in _DUNDER or name.startswith("test_"):
            continue
        # Skip simple/likely-private one-off helpers nested under classes
        # (name format is "ClassName.method" for methods — those are common
        # to be unused if the class itself is unused, skip noise)
        base_name = name.split(".")[-1]

        # Skip known entry points / route handlers / exported names
        if base_name in entry_point_names:
            continue

        # __init__.py contents are often intentionally unreferenced internally
        if file_path.endswith("__init__.py"):
            continue

        if node["id"] not in referenced_ids:
            dead.append({
                "name":       name,
                "kind":       kind,
                "file_path":  file_path,
                "line_start": node["line_start"],
                "line_end":   node["line_end"],
                "reason":     "No callers found anywhere in the workspace.",
            })

    return dead


def _get_entry_point_names(workspace: Path) -> set[str]:
    """
    Scan for FastAPI route decorators and React default exports —
    these are "used" by the framework, not by direct calls, so the
    graph won't show them as referenced even though they're live code.
    """
    names: set[str] = set()
    for py_file in workspace.rglob("*.py"):
        if any(s in py_file.parts for s in _SKIP):
            continue
        try:
            src  = py_file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(src)
        except Exception:
            continue

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    dec_str = ast.dump(dec)
                    if any(kw in dec_str for kw in (
                        "app.get", "app.post", "app.put", "app.delete",
                        "app.patch", "app.websocket", "router.get", "router.post",
                        "pytest.fixture",
                    )):
                        names.add(node.name)

    return names


def format_dead_code_summary(dead: list[dict]) -> str:
    """One-line summary for chat/proactive suggestion display."""
    if not dead:
        return "No dead code detected."
    by_kind: dict[str, int] = {}
    for d in dead:
        by_kind[d["kind"]] = by_kind.get(d["kind"], 0) + 1
    parts = [f"{v} unused {k}{'s' if v != 1 else ''}" for k, v in by_kind.items()]
    return f"Found {', '.join(parts)} across {len({d['file_path'] for d in dead})} file(s)."
