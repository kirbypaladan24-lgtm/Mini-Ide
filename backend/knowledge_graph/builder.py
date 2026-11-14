"""
knowledge_graph/builder.py — Mini IDE Milestone B

Builds a SQLite relationship graph from the workspace source files.
Nodes: functions, classes, files, imports.
Edges: calls, defines, imports, inherits.

Runs as a background task after workspace indexing (Phase 4) completes.
"""
from __future__ import annotations

import ast
import hashlib
import sqlite3
from pathlib import Path

# Directories to skip (mirrors file_ops._SKIP)
_SKIP = frozenset({
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "dist", "build", ".next", ".idea", ".vscode",
})

_SCHEMA = """
CREATE TABLE IF NOT EXISTS kg_nodes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    kind       TEXT    NOT NULL,   -- function | class | file | import
    file_path  TEXT    NOT NULL,
    line_start INTEGER DEFAULT 0,
    line_end   INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS kg_edges (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id      INTEGER NOT NULL REFERENCES kg_nodes(id) ON DELETE CASCADE,
    to_id        INTEGER NOT NULL REFERENCES kg_nodes(id) ON DELETE CASCADE,
    relationship TEXT    NOT NULL  -- calls | defines | imports | inherits
);

CREATE INDEX IF NOT EXISTS idx_kg_nodes_name ON kg_nodes(name);
CREATE INDEX IF NOT EXISTS idx_kg_nodes_file ON kg_nodes(file_path);
CREATE INDEX IF NOT EXISTS idx_kg_edges_from ON kg_edges(from_id);
CREATE INDEX IF NOT EXISTS idx_kg_edges_to   ON kg_edges(to_id);
"""

_CACHE_ROOT = Path(__file__).parent.parent / ".rag_cache"


def db_path_for(workspace: Path) -> Path:
    h = hashlib.md5(str(workspace.resolve()).encode()).hexdigest()[:10]
    d = _CACHE_ROOT / h
    d.mkdir(parents=True, exist_ok=True)
    return d / "graph.db"


def build_graph(workspace: Path) -> Path:
    """
    Walk the workspace, extract relationships, write to SQLite.
    Returns the path to the graph database.
    """
    db = db_path_for(workspace)
    conn = sqlite3.connect(str(db))
    conn.executescript(_SCHEMA)
    conn.execute("DELETE FROM kg_edges")
    conn.execute("DELETE FROM kg_nodes")
    conn.commit()

    for py_file in workspace.rglob("*.py"):
        if any(s in py_file.parts for s in _SKIP):
            continue
        if py_file.name.startswith("."):
            continue
        try:
            _index_python_file(conn, py_file, workspace)
        except Exception:
            pass

    conn.commit()
    conn.close()
    return db


# ── Python AST indexer ────────────────────────────────────────────────────────
def _index_python_file(conn: sqlite3.Connection, path: Path, workspace: Path) -> None:
    rel = str(path.resolve().relative_to(workspace.resolve())).replace("\\", "/")
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree   = ast.parse(source)
    except Exception:
        return

    # File node
    file_id = _insert_node(conn, rel, "file", rel, 0, 0)

    # Top-level and class-level symbols
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn_id = _insert_node(
                conn, node.name, "function", rel,
                node.lineno, getattr(node, "end_lineno", node.lineno)
            )
            _insert_edge(conn, file_id, fn_id, "defines")
            # Record calls made inside this function
            _record_calls(conn, fn_id, node)

        elif isinstance(node, ast.ClassDef):
            cls_id = _insert_node(
                conn, node.name, "class", rel,
                node.lineno, getattr(node, "end_lineno", node.lineno)
            )
            _insert_edge(conn, file_id, cls_id, "defines")
            # Inheritance
            for base in node.bases:
                base_name = _name_of(base)
                if base_name:
                    base_id = _get_or_create_node(conn, base_name, "class", "")
                    _insert_edge(conn, cls_id, base_id, "inherits")
            # Methods
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    m_id = _insert_node(
                        conn, f"{node.name}.{child.name}", "function", rel,
                        child.lineno, getattr(child, "end_lineno", child.lineno)
                    )
                    _insert_edge(conn, cls_id, m_id, "defines")

        elif isinstance(node, ast.Import):
            for alias in node.names:
                imp_id = _get_or_create_node(conn, alias.name, "import", "")
                _insert_edge(conn, file_id, imp_id, "imports")

        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod:
                imp_id = _get_or_create_node(conn, mod, "import", "")
                _insert_edge(conn, file_id, imp_id, "imports")


def _record_calls(conn: sqlite3.Connection, caller_id: int, func_node: ast.AST) -> None:
    """Record function calls made inside func_node."""
    for child in ast.walk(func_node):
        if isinstance(child, ast.Call):
            name = _name_of(child.func)
            if name and "." not in name:  # only simple name calls for now
                callee_id = _get_or_create_node(conn, name, "function", "")
                _insert_edge(conn, caller_id, callee_id, "calls")


# ── SQLite helpers ────────────────────────────────────────────────────────────
def _insert_node(
    conn: sqlite3.Connection,
    name: str, kind: str, file_path: str,
    line_start: int, line_end: int,
) -> int:
    cur = conn.execute(
        "INSERT INTO kg_nodes (name, kind, file_path, line_start, line_end)"
        " VALUES (?,?,?,?,?)",
        (name, kind, file_path, line_start, line_end),
    )
    return cur.lastrowid


def _get_or_create_node(
    conn: sqlite3.Connection, name: str, kind: str, file_path: str
) -> int:
    row = conn.execute(
        "SELECT id FROM kg_nodes WHERE name=? AND kind=?", (name, kind)
    ).fetchone()
    if row:
        return row[0]
    return _insert_node(conn, name, kind, file_path, 0, 0)


def _insert_edge(
    conn: sqlite3.Connection, from_id: int, to_id: int, relationship: str
) -> None:
    # Avoid duplicate edges
    exists = conn.execute(
        "SELECT 1 FROM kg_edges WHERE from_id=? AND to_id=? AND relationship=?",
        (from_id, to_id, relationship),
    ).fetchone()
    if not exists:
        conn.execute(
            "INSERT INTO kg_edges (from_id, to_id, relationship) VALUES (?,?,?)",
            (from_id, to_id, relationship),
        )


def _name_of(node: ast.expr) -> str | None:
    """Extract a dotted name from an AST expression."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _name_of(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None
