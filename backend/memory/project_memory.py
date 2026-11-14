"""
memory/project_memory.py — Mini IDE Sprint 5

Separate from the per-language preference learner (Milestone C).
This stores explicit, durable facts about THIS project that should
inform AI behavior in every future session — not statistical signals,
but stated decisions:

  "This project uses SQLite, not PostgreSQL"
  "Authentication logic only lives in auth.py"
  "API returns camelCase JSON but Python uses snake_case internally"

Populated two ways:
  1. Explicit: user says "remember that we always use httpx"
  2. Implicit: a future enhancement could auto-extract from repeated
     planner observations — not implemented yet, kept simple by design.

Stored in backend/.project_memory.db, one row per memory, with a
naive keyword-overlap retrieval (no embeddings — this is meant to be
small, ~20-50 entries, so brute-force is fine and avoids another
dependency).
"""
from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

_DB = Path(__file__).parent.parent / ".project_memory.db"

_CATEGORIES = frozenset({"architecture", "convention", "decision", "preference", "warning"})

_REMEMBER_TRIGGER = re.compile(
    r"\b(remember that|note that|keep in mind|always|never)\b",
    re.IGNORECASE,
)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_memory (
            id       TEXT PRIMARY KEY,
            ts       TEXT NOT NULL,
            category TEXT NOT NULL,
            text     TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def store(text: str, category: str = "decision") -> str:
    """Store a new memory. Returns the entry id."""
    if category not in _CATEGORIES:
        category = "decision"
    entry_id = uuid.uuid4().hex[:10]
    conn = _conn()
    conn.execute(
        "INSERT INTO project_memory (id, ts, category, text) VALUES (?,?,?,?)",
        (entry_id, datetime.now().isoformat(), category, text.strip()[:500]),
    )
    conn.commit()
    conn.close()
    return entry_id


def list_all() -> list[dict]:
    conn = _conn()
    rows = conn.execute(
        "SELECT id, ts, category, text FROM project_memory ORDER BY ts DESC"
    ).fetchall()
    conn.close()
    return [{"id": r[0], "ts": r[1], "category": r[2], "text": r[3]} for r in rows]


def delete(entry_id: str) -> bool:
    conn = _conn()
    cur = conn.execute("DELETE FROM project_memory WHERE id = ?", (entry_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def recall(query: str, k: int = 5) -> list[dict]:
    """
    Naive keyword-overlap retrieval — good enough for ~20-50 entries.
    Returns the k entries with the most word overlap with the query.
    """
    all_memories = list_all()
    if not all_memories:
        return []

    query_words = set(re.findall(r"\w+", query.lower()))
    scored = []
    for mem in all_memories:
        mem_words = set(re.findall(r"\w+", mem["text"].lower()))
        overlap = len(query_words & mem_words)
        if overlap > 0:
            scored.append((overlap, mem))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored[:k]]


def build_context() -> str:
    """
    Return ALL memories as a compact context block — always injected
    into the codebase summary since the list is meant to stay small.
    Empty string if nothing stored yet.
    """
    memories = list_all()
    if not memories:
        return ""
    lines = [f"- [{m['category']}] {m['text']}" for m in memories[:30]]
    return "Project notes (from previous sessions):\n" + "\n".join(lines)


def detect_remember_request(message: str) -> str | None:
    """
    If the user's message looks like an explicit "remember this" request,
    extract the fact to store. Returns None if it doesn't match.
    """
    if not _REMEMBER_TRIGGER.search(message):
        return None
    # Strip the trigger phrase itself, keep the rest as the fact
    cleaned = _REMEMBER_TRIGGER.sub("", message, count=1).strip()
    cleaned = cleaned.lstrip(":,- ").strip()
    return cleaned if len(cleaned) > 5 else None
