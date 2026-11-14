"""
knowledge_graph/architecture.py — Mini IDE Milestone E

Higher-level views built on top of the Milestone B knowledge graph:
  - get_entry_points():     where execution starts
  - get_core_modules():     most-depended-on local files
  - get_dependency_chain(): what a file imports
  - diff_changed_symbols(): which functions/classes actually changed
                             between two versions of a file (for impact
                             analysis before applying an AI edit)
"""
from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

from knowledge_graph.builder import db_path_for

_ENTRY_POINT_NAMES = {"main.py", "app.py", "__main__.py", "manage.py", "run.py", "server.py"}


def _conn(workspace: Path) -> sqlite3.Connection | None:
    db = db_path_for(workspace)
    if not db.exists():
        return None
    try:
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        return None


# ── Entry points ──────────────────────────────────────────────────────────────
def get_entry_points(workspace: Path) -> list[dict]:
    """
    Return files likely to be execution entry points:
    conventional names (main.py, app.py, ...) or files containing
    `if __name__ == "__main__"`.
    """
    conn = _conn(workspace)
    if not conn:
        return []
    try:
        rows = conn.execute(
            "SELECT DISTINCT file_path FROM kg_nodes WHERE kind='file'"
        ).fetchall()
    except Exception:
        conn.close()
        return []
    conn.close()

    entries = []
    for row in rows:
        rel  = row["file_path"]
        name = Path(rel).name
        if name in _ENTRY_POINT_NAMES:
            entries.append({"file_path": rel, "reason": f"conventional name: {name}"})
            continue
        try:
            abs_path = (workspace / rel).resolve()
            if abs_path.exists():
                text = abs_path.read_text(encoding="utf-8", errors="replace")
                if '__name__ == "__main__"' in text or "__name__ == '__main__'" in text:
                    entries.append({"file_path": rel, "reason": "has __main__ guard"})
        except Exception:
            continue

    return entries


# ── Core modules ──────────────────────────────────────────────────────────────
def get_core_modules(workspace: Path, limit: int = 10) -> list[dict]:
    """
    Rank local files by how many other files import them, approximated
    by matching import node names against file stems in the workspace.
    """
    conn = _conn(workspace)
    if not conn:
        return []
    try:
        files = conn.execute(
            "SELECT id, file_path FROM kg_nodes WHERE kind='file'"
        ).fetchall()

        ranked = []
        for f in files:
            stem = Path(f["file_path"]).stem
            dotted = Path(f["file_path"]).with_suffix("").as_posix().replace("/", ".")
            count_row = conn.execute("""
                SELECT COUNT(*) FROM kg_edges e
                JOIN kg_nodes t ON e.to_id = t.id
                WHERE e.relationship = 'imports'
                  AND (t.name = ? OR t.name = ? OR t.name LIKE ?)
            """, (stem, dotted, f"%.{stem}")).fetchone()[0]

            if count_row > 0:
                ranked.append({"file_path": f["file_path"], "imported_by_count": count_row})

        ranked.sort(key=lambda x: x["imported_by_count"], reverse=True)
        return ranked[:limit]
    except Exception:
        return []
    finally:
        conn.close()


# ── Dependency chain ───────────────────────────────────────────────────────────
def get_dependency_chain(file_path: str, workspace: Path) -> list[str]:
    """Return the names of everything `file_path` imports."""
    conn = _conn(workspace)
    if not conn:
        return []
    try:
        rows = conn.execute("""
            SELECT DISTINCT t.name
            FROM   kg_nodes n
            JOIN   kg_edges e ON e.from_id = n.id
            JOIN   kg_nodes t ON e.to_id   = t.id
            WHERE  n.file_path = ? AND n.kind = 'file' AND e.relationship = 'imports'
        """, (file_path,)).fetchall()
        return [r["name"] for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


# ── Changed-symbol detection (for impact analysis before apply) ──────────────
def diff_changed_symbols(original: str, proposed: str, language: str) -> list[str]:
    """
    Compare two versions of a Python file and return the names of
    functions/classes whose source actually changed (or were removed).
    Used to scope impact_analysis() to only the symbols genuinely affected.
    Returns [] for non-Python languages or on any parse failure.
    """
    if language != "python":
        return []

    try:
        orig_symbols = _extract_symbol_sources(original)
        new_symbols  = _extract_symbol_sources(proposed)
    except Exception:
        return []

    changed = []
    for name, orig_src in orig_symbols.items():
        new_src = new_symbols.get(name)
        if new_src is None:
            changed.append(name)          # removed
        elif new_src.strip() != orig_src.strip():
            changed.append(name)          # modified

    return changed


def _extract_symbol_sources(source: str) -> dict[str, str]:
    """Map function/class name → its source segment."""
    tree = ast.parse(source)
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            seg = ast.get_source_segment(source, node)
            if seg:
                out[node.name] = seg
    return out
