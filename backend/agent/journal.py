"""
agent/journal.py — Mini IDE Milestone D

Records every agent pipeline execution: which specialists ran, why,
what they found, and how long each step took. Powers the Agent Log
view in the frontend (transparency into what the AI actually did).
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

_DB = Path(__file__).parent.parent / ".agent_journal.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS journal_tasks (
            id          TEXT PRIMARY KEY,
            ts          TEXT NOT NULL,
            request     TEXT NOT NULL,
            file_path   TEXT DEFAULT '',
            agents_run  TEXT DEFAULT '[]',   -- JSON list
            steps       TEXT DEFAULT '[]',   -- JSON list of step dicts
            total_ms    INTEGER DEFAULT 0,
            outcome     TEXT DEFAULT 'pending'
        )
    """)
    conn.commit()
    return conn


class TaskJournal:
    """
    Accumulates steps for a single task, then writes them all at once.

    Usage:
        journal = TaskJournal(request="refactor auth", file_path="auth.py")
        with journal.step("verify") as s:
            ... do work ...
            s.note("syntax ok")
        journal.finish(outcome="applied")
    """

    def __init__(self, request: str, file_path: str = ""):
        self.id        = uuid.uuid4().hex[:12]
        self.request   = request
        self.file_path = file_path
        self.steps:  list[dict] = []
        self.agents: list[str]  = []
        self._start = time.monotonic()

    @contextmanager
    def step(self, agent: str, reason: str = "", model: str = ""):
        """Context manager that times a single agent step and records it."""
        t0 = time.monotonic()
        recorder = _StepRecorder()
        self.agents.append(agent)
        try:
            yield recorder
        finally:
            duration_ms = int((time.monotonic() - t0) * 1000)
            self.steps.append({
                "agent":       agent,
                "model":       model,
                "reason":      reason,
                "duration_ms": duration_ms,
                "notes":       recorder.notes,
                "findings":    recorder.findings,
            })

    def finish(self, outcome: str = "applied") -> None:
        """Write the completed task to SQLite."""
        total_ms = int((time.monotonic() - self._start) * 1000)
        conn = _connect()
        conn.execute("""
            INSERT INTO journal_tasks (id, ts, request, file_path, agents_run, steps, total_ms, outcome)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            self.id, datetime.now().isoformat(), self.request, self.file_path,
            json.dumps(self.agents), json.dumps(self.steps), total_ms, outcome,
        ))
        conn.commit()
        conn.close()


class _StepRecorder:
    """Passed into each `with journal.step(...)` block for the caller to annotate."""
    def __init__(self):
        self.notes:    list[str] = []
        self.findings: list[str] = []

    def note(self, text: str) -> None:
        self.notes.append(text)

    def finding(self, text: str) -> None:
        self.findings.append(text)


# ── Query interface ────────────────────────────────────────────────────────────
def get_recent(limit: int = 40) -> list[dict]:
    """Return the most recent journal entries, newest first."""
    conn = _connect()
    rows = conn.execute("""
        SELECT id, ts, request, file_path, agents_run, steps, total_ms, outcome
        FROM   journal_tasks
        ORDER  BY id DESC
        LIMIT  ?
    """, (limit,)).fetchall()
    conn.close()

    return [
        {
            "id":         r[0],
            "ts":         r[1],
            "request":    r[2],
            "file_path":  r[3],
            "agents_run": json.loads(r[4]),
            "steps":      json.loads(r[5]),
            "total_ms":   r[6],
            "outcome":    r[7],
        }
        for r in rows
    ]


def get_stats() -> dict:
    """Aggregate stats for a quick dashboard summary."""
    conn = _connect()
    row = conn.execute("""
        SELECT COUNT(*), AVG(total_ms), SUM(CASE WHEN outcome='applied' THEN 1 ELSE 0 END)
        FROM journal_tasks
    """).fetchone()
    total, avg_ms, applied = row

    # Milestone F: per-model and per-agent breakdown for observability
    model_counts: dict[str, dict] = {}
    agent_counts: dict[str, int]  = {}

    rows = conn.execute("SELECT steps, outcome FROM journal_tasks ORDER BY id DESC LIMIT 200").fetchall()
    conn.close()

    for steps_json, outcome in rows:
        try:
            steps = json.loads(steps_json)
        except Exception:
            continue
        for s in steps:
            agent = s.get("agent", "?")
            agent_counts[agent] = agent_counts.get(agent, 0) + 1

            model = s.get("model", "")
            if not model:
                continue
            if model not in model_counts:
                model_counts[model] = {"runs": 0, "applied": 0}
            model_counts[model]["runs"] += 1
            if outcome == "applied":
                model_counts[model]["applied"] += 1

    model_stats = [
        {
            "model": m, "runs": v["runs"], "applied": v["applied"],
            "success_rate": round(100 * v["applied"] / v["runs"], 1) if v["runs"] else 0,
        }
        for m, v in model_counts.items()
    ]
    model_stats.sort(key=lambda x: x["runs"], reverse=True)

    return {
        "total_tasks":  total or 0,
        "avg_ms":       int(avg_ms) if avg_ms else 0,
        "applied":      applied or 0,
        "model_stats":  model_stats,
        "agent_counts": agent_counts,
    }
