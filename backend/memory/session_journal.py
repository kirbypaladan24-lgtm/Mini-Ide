"""
memory/session_journal.py — Mini IDE Sprint 4

Tracks every AI-applied file change, grouped by "feature" (one
user request = one feature_id). Powers the session timeline and
feature-level rollback.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import date, datetime
from pathlib import Path

_DB = Path(__file__).parent.parent / ".session_journal.db"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS session_entries (
            id            TEXT PRIMARY KEY,
            feature_id    TEXT NOT NULL,
            ts            TEXT NOT NULL,
            request       TEXT NOT NULL DEFAULT '',
            file_path     TEXT NOT NULL,
            description   TEXT NOT NULL DEFAULT '',
            checkpoint_id TEXT NOT NULL DEFAULT '',
            language      TEXT NOT NULL DEFAULT '',
            lines_added   INTEGER DEFAULT 0,
            lines_removed INTEGER DEFAULT 0,
            outcome       TEXT NOT NULL DEFAULT 'applied'
        )
    """)
    conn.commit()
    return conn


def new_feature_id() -> str:
    return uuid.uuid4().hex[:12]


def record_file_change(
    feature_id:    str,
    request:       str,
    file_path:     str,
    original:      str,
    updated:       str,
    checkpoint_id: str,
    language:      str = "",
    description:   str = "",
    outcome:       str = "applied",
) -> str:
    entry_id      = uuid.uuid4().hex[:10]
    orig_lines    = original.count("\n") if original else 0
    upd_lines     = updated.count("\n")  if updated  else 0
    added         = max(0, upd_lines - orig_lines)
    removed       = max(0, orig_lines - upd_lines)
    desc          = description or f"AI edit → {file_path}"

    conn = _conn()
    conn.execute("""
        INSERT INTO session_entries
          (id, feature_id, ts, request, file_path, description,
           checkpoint_id, language, lines_added, lines_removed, outcome)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (
        entry_id, feature_id, datetime.now().isoformat(),
        request[:300], file_path, desc[:300],
        checkpoint_id, language, added, removed, outcome,
    ))
    conn.commit()
    conn.close()
    return entry_id


def get_today_features() -> list[dict]:
    today = date.today().isoformat()
    conn  = _conn()
    rows  = conn.execute("""
        SELECT id, feature_id, ts, request, file_path, description,
               checkpoint_id, language, lines_added, lines_removed, outcome
        FROM   session_entries
        WHERE  ts >= ?
        ORDER  BY ts DESC
    """, (today,)).fetchall()
    conn.close()

    features: dict[str, dict] = {}
    for (eid, fid, ts, req, fp, desc, cp_id, lang, added, removed, outcome) in rows:
        if fid not in features:
            features[fid] = {"feature_id": fid, "request": req, "ts": ts, "files": []}
        features[fid]["files"].append({
            "id": eid, "file_path": fp, "description": desc,
            "checkpoint_id": cp_id, "language": lang,
            "lines_added": added, "lines_removed": removed,
            "outcome": outcome, "ts": ts,
        })

    return list(features.values())


def get_checkpoint_ids_for_feature(feature_id: str) -> list[tuple[str, str]]:
    conn = _conn()
    rows = conn.execute("""
        SELECT file_path, checkpoint_id FROM session_entries
        WHERE  feature_id = ? AND checkpoint_id != ''
    """, (feature_id,)).fetchall()
    conn.close()
    return [(r[0], r[1]) for r in rows]
