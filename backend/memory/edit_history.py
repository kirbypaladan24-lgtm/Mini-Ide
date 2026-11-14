"""
memory/edit_history.py — Mini IDE Phase 6

Persistent SQLite undo stack for AI-applied edits.
Every write that comes from the AI (chat apply, auto-fix, multi-file patch)
is recorded here with its original content so it can be reverted instantly.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

_DB = Path(__file__).parent.parent / ".edit_history.db"


# ── Schema setup ──────────────────────────────────────────────────────────────
def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS edits (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT    NOT NULL,
            file_path   TEXT    NOT NULL,
            original    TEXT    NOT NULL,
            updated     TEXT    NOT NULL,
            source      TEXT    DEFAULT 'ai',
            description TEXT    DEFAULT '',
            workspace   TEXT    DEFAULT '',
            reverted    INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    return conn


# ── Write ─────────────────────────────────────────────────────────────────────
def record_edit(
    file_path:   str,
    original:    str,
    updated:     str,
    source:      str = "ai",
    description: str = "",
    workspace:   str = "",
) -> int:
    """
    Persist a before/after snapshot.  Returns the new edit ID.
    Called whenever the AI writes to a file (chat apply, auto-fix, patch).
    Manual Ctrl+S saves are NOT recorded here.
    """
    conn = _connect()
    cur  = conn.execute(
        "INSERT INTO edits (ts, file_path, original, updated, source, description, workspace)"
        " VALUES (?,?,?,?,?,?,?)",
        (datetime.now().isoformat(), file_path, original, updated,
         source, description, workspace),
    )
    edit_id = cur.lastrowid
    conn.commit()
    conn.close()
    return edit_id


# ── Read ──────────────────────────────────────────────────────────────────────
def get_history(workspace: str = "", limit: int = 60) -> list[dict]:
    """Return recent edits, newest first."""
    conn = _connect()
    rows = conn.execute(
        "SELECT id, ts, file_path, source, description, reverted,"
        "       length(original), length(updated)"
        " FROM  edits"
        " WHERE (? = '' OR workspace = ?)"
        " ORDER BY id DESC LIMIT ?",
        (workspace, workspace, limit),
    ).fetchall()
    conn.close()

    return [
        {
            "id":          r[0],
            "ts":          r[1],
            "file_path":   r[2],
            "source":      r[3],
            "description": r[4] or "",
            "reverted":    bool(r[5]),
            "orig_size":   r[6],
            "upd_size":    r[7],
        }
        for r in rows
    ]


# ── Undo ──────────────────────────────────────────────────────────────────────
def undo_edit(edit_id: int) -> Optional[dict]:
    """
    Mark an edit as reverted and return {file_path, content} to restore.
    Returns None if the edit doesn't exist or was already reverted.
    """
    conn = _connect()
    row  = conn.execute(
        "SELECT file_path, original, reverted FROM edits WHERE id = ?", (edit_id,)
    ).fetchone()

    if not row:
        conn.close()
        return None
    file_path, original, already_reverted = row
    if already_reverted:
        conn.close()
        return None

    conn.execute("UPDATE edits SET reverted = 1 WHERE id = ?", (edit_id,))
    conn.commit()
    conn.close()
    return {"file_path": file_path, "content": original}
