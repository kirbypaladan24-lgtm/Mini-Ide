"""
memory/model_benchmark.py — Mini IDE Milestone G

Tracks how well each model actually performs per task type on THIS
machine, based on real outcomes (accepted, revised, rejected) rather
than benchmarks from someone else's hardware. Over time this lets the
IDE suggest the empirically best model for a given task instead of a
hardcoded default.

quality_score per outcome:
  accept  → 1.0  (user applied it as-is)
  revised → 0.7  (critic had to revise it before it was good)
  reject  → 0.0  (user cancelled)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

_DB = Path(__file__).parent.parent / ".model_benchmark.db"

_QUALITY = {"accept": 1.0, "revised": 0.7, "reject": 0.0}
_MIN_SAMPLES_FOR_SUGGESTION = 4   # don't suggest based on tiny sample sizes


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS model_benchmark (
            model         TEXT NOT NULL,
            task_type     TEXT NOT NULL,
            runs          INTEGER DEFAULT 0,
            total_quality REAL    DEFAULT 0.0,
            total_ms      INTEGER DEFAULT 0,
            PRIMARY KEY (model, task_type)
        )
    """)
    conn.commit()
    return conn


def record_outcome(
    model:       str,
    task_type:   str,
    outcome:     str,    # "accept" | "revised" | "reject"
    duration_ms: int = 0,
) -> None:
    """Record one real-world outcome for a model on a task type."""
    quality = _QUALITY.get(outcome, 0.0)
    conn = _connect()
    conn.execute("""
        INSERT INTO model_benchmark (model, task_type, runs, total_quality, total_ms)
        VALUES (?, ?, 1, ?, ?)
        ON CONFLICT(model, task_type)
        DO UPDATE SET
            runs          = runs + 1,
            total_quality = total_quality + ?,
            total_ms      = total_ms + ?
    """, (model, task_type, quality, duration_ms, quality, duration_ms))
    conn.commit()
    conn.close()


def get_best_model(task_type: str) -> dict | None:
    """
    Return the empirically best-performing model for this task type,
    or None if there isn't enough data yet to make a confident call.
    """
    conn = _connect()
    rows = conn.execute("""
        SELECT model, runs, total_quality, total_ms
        FROM   model_benchmark
        WHERE  task_type = ? AND runs >= ?
        ORDER  BY (total_quality / runs) DESC
        LIMIT  1
    """, (task_type, _MIN_SAMPLES_FOR_SUGGESTION)).fetchone()
    conn.close()

    if not rows:
        return None
    model, runs, total_quality, total_ms = rows
    return {
        "model":       model,
        "runs":        runs,
        "avg_quality": round(total_quality / runs, 2),
        "avg_ms":      int(total_ms / runs) if runs else 0,
    }


def get_all_stats() -> list[dict]:
    """Return every model/task_type combination tracked, for display."""
    conn = _connect()
    rows = conn.execute("""
        SELECT model, task_type, runs, total_quality, total_ms
        FROM   model_benchmark
        ORDER  BY runs DESC
    """).fetchall()
    conn.close()

    return [
        {
            "model":       m,
            "task_type":   t,
            "runs":        r,
            "avg_quality": round(q / r, 2) if r else 0,
            "avg_ms":      int(ms / r) if r else 0,
        }
        for m, t, r, q, ms in rows
    ]
