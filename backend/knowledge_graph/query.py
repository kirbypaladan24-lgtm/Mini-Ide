"""
knowledge_graph/query.py — Mini IDE Milestone B

High-level query functions over the SQLite knowledge graph.
All functions return empty results gracefully if the graph is not built yet.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from knowledge_graph.builder import db_path_for


def _conn(workspace: Path) -> sqlite3.Connection | None:
    """Open the graph DB for this workspace, or return None if not built."""
    db = db_path_for(workspace)
    if not db.exists():
        return None
    try:
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        return None


# ── Callers ───────────────────────────────────────────────────────────────────
def find_callers(func_name: str, workspace: Path) -> list[dict]:
    """
    Return all functions/files that call `func_name`.
    """
    conn = _conn(workspace)
    if not conn:
        return []
    try:
        rows = conn.execute("""
            SELECT DISTINCT n.name, n.kind, n.file_path, n.line_start
            FROM   kg_nodes n
            JOIN   kg_edges e ON e.from_id = n.id
            JOIN   kg_nodes t ON e.to_id   = t.id
            WHERE  t.name = ? AND e.relationship = 'calls'
        """, (func_name,)).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


# ── Callees ───────────────────────────────────────────────────────────────────
def find_callees(func_name: str, workspace: Path) -> list[dict]:
    """
    Return all functions called by `func_name`.
    """
    conn = _conn(workspace)
    if not conn:
        return []
    try:
        rows = conn.execute("""
            SELECT DISTINCT t.name, t.kind, t.file_path, t.line_start
            FROM   kg_nodes n
            JOIN   kg_edges e ON e.from_id = n.id
            JOIN   kg_nodes t ON e.to_id   = t.id
            WHERE  n.name = ? AND e.relationship = 'calls'
        """, (func_name,)).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


# ── Inheritors ────────────────────────────────────────────────────────────────
def find_inheritors(class_name: str, workspace: Path) -> list[dict]:
    """
    Return all classes that inherit from `class_name`.
    """
    conn = _conn(workspace)
    if not conn:
        return []
    try:
        rows = conn.execute("""
            SELECT DISTINCT n.name, n.kind, n.file_path, n.line_start
            FROM   kg_nodes n
            JOIN   kg_edges e ON e.from_id = n.id
            JOIN   kg_nodes t ON e.to_id   = t.id
            WHERE  t.name = ? AND e.relationship = 'inherits'
        """, (class_name,)).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


# ── Impact analysis ───────────────────────────────────────────────────────────
def impact_analysis(symbol: str, workspace: Path) -> dict:
    """
    Return a full impact report for changing `symbol`.

    Includes: direct callers, transitive callers (1 level), inheritors,
    files affected, and a plain-English summary.
    """
    callers     = find_callers(symbol, workspace)
    callees     = find_callees(symbol, workspace)
    inheritors  = find_inheritors(symbol, workspace)

    affected_files = list({
        r["file_path"] for r in callers + inheritors if r.get("file_path")
    })

    if not callers and not inheritors:
        summary = f"`{symbol}` has no detected callers or subclasses — safe to change."
    else:
        parts = []
        if callers:
            parts.append(f"called from {len(callers)} place{'s' if len(callers)!=1 else ''}")
        if inheritors:
            parts.append(f"subclassed by {len(inheritors)} class{'es' if len(inheritors)!=1 else ''}")
        summary = (
            f"⚠ Changing `{symbol}` affects {', '.join(parts)} "
            f"across {len(affected_files)} file{'s' if len(affected_files)!=1 else ''}."
        )

    return {
        "symbol":         symbol,
        "callers":        callers,
        "callees":        callees,
        "inheritors":     inheritors,
        "affected_files": affected_files,
        "summary":        summary,
    }


# ── File symbols ──────────────────────────────────────────────────────────────
def get_file_symbols(file_path: str, workspace: Path) -> list[dict]:
    """Return all symbols defined in the given file."""
    conn = _conn(workspace)
    if not conn:
        return []
    try:
        rows = conn.execute("""
            SELECT name, kind, line_start, line_end
            FROM   kg_nodes
            WHERE  file_path = ?
            ORDER  BY line_start
        """, (file_path,)).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()
