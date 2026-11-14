"""
memory/preference_learner.py — Mini IDE Milestone C

Passively learns coding preferences by detecting known signal patterns
in code the user accepts vs. rejects from the AI. Builds a short context
string that gets prepended to every prompt so the AI stops suggesting
things this developer consistently rejects.

This is intentionally lightweight — a fixed signal list with regex
matching, not a learned model. Accurate enough to be useful, simple
enough to audit and extend.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

_DB = Path(__file__).parent.parent / ".preferences.db"

# ── Known preference signals ──────────────────────────────────────────────────
# Each signal is (name, regex, human-readable label, language or "" for any)
_SIGNALS: list[tuple[str, re.Pattern, str, str]] = [
    ("httpx",          re.compile(r"\bimport httpx\b"),                "use httpx for HTTP requests", "python"),
    ("requests_lib",    re.compile(r"\bimport requests\b"),              "use requests for HTTP",        "python"),
    ("type_hints",      re.compile(r"def \w+\([^)]*:\s*\w+"),            "always add type hints",        "python"),
    ("async_def",        re.compile(r"\basync def\b"),                   "prefer async functions",       "python"),
    ("dataclass",        re.compile(r"@dataclass"),                      "use dataclasses",               "python"),
    ("pydantic",         re.compile(r"\bBaseModel\b"),                   "use Pydantic models",           "python"),
    ("f_string",         re.compile(r'f["\']'),                          "use f-strings",                 "python"),
    ("bare_except",      re.compile(r"except\s*:\s*\n"),                 "avoid bare except", "python"),
    ("specific_except",  re.compile(r"except \w+(Error|Exception)\b"),   "use specific exception types", "python"),
    ("const_let",        re.compile(r"\b(const|let)\b"),                 "use const/let over var",        "javascript"),
    ("var_decl",         re.compile(r"\bvar\s+\w+\s*="),                 "uses var declarations",         "javascript"),
    ("arrow_fn",         re.compile(r"=>\s*[{(]"),                       "prefer arrow functions",        "javascript"),
    ("optional_chain",   re.compile(r"\?\."),                            "use optional chaining",         "javascript"),
]


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pref_signals (
            signal        TEXT NOT NULL,
            language      TEXT NOT NULL,
            accept_count  INTEGER DEFAULT 0,
            reject_count  INTEGER DEFAULT 0,
            suggested     INTEGER DEFAULT 0,
            PRIMARY KEY (signal, language)
        )
    """)
    # Milestone G: migrate older DBs that predate the 'suggested' column
    try:
        conn.execute("ALTER TABLE pref_signals ADD COLUMN suggested INTEGER DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass   # column already exists
    conn.commit()
    return conn


def _detect_signals(code: str, language: str) -> list[str]:
    found = []
    for name, pattern, _, sig_lang in _SIGNALS:
        if sig_lang and sig_lang != language:
            continue
        if pattern.search(code):
            found.append(name)
    return found


def _bump(conn: sqlite3.Connection, signal: str, language: str, field: str) -> None:
    conn.execute(f"""
        INSERT INTO pref_signals (signal, language, {field})
        VALUES (?, ?, 1)
        ON CONFLICT(signal, language)
        DO UPDATE SET {field} = {field} + 1
    """, (signal, language))


# ── Public API ────────────────────────────────────────────────────────────────
def record_accept(proposed: str, language: str) -> None:
    """Call when the user clicks Apply on an AI suggestion."""
    signals = _detect_signals(proposed, language)
    if not signals:
        return
    conn = _connect()
    for s in signals:
        _bump(conn, s, language, "accept_count")
    conn.commit()
    conn.close()


def record_reject(proposed: str, language: str) -> None:
    """Call when the user clicks Cancel on an AI suggestion."""
    signals = _detect_signals(proposed, language)
    if not signals:
        return
    conn = _connect()
    for s in signals:
        _bump(conn, s, language, "reject_count")
    conn.commit()
    conn.close()


def get_preference_context(language: str, min_net: int = 2) -> str:
    """
    Return a short prompt-ready string of learned preferences for this
    language, or "" if not enough data has accumulated yet.
    """
    conn = _connect()
    rows = conn.execute("""
        SELECT signal, accept_count, reject_count
        FROM   pref_signals
        WHERE  language = ?
    """, (language,)).fetchall()
    conn.close()

    if not rows:
        return ""

    label_map = {name: label for name, _, label, _ in _SIGNALS}
    prefers:  list[str] = []
    avoids:   list[str] = []

    for signal, accept, reject in rows:
        net = accept - reject
        label = label_map.get(signal, signal)
        if net >= min_net:
            prefers.append(label)
        elif net <= -min_net:
            avoids.append(label)

    if not prefers and not avoids:
        return ""

    parts = []
    if prefers:
        parts.append("This developer prefers: " + ", ".join(prefers) + ".")
    if avoids:
        parts.append("Avoid: " + ", ".join(avoids) + ".")
    return " ".join(parts)


def get_stats() -> list[dict]:
    """Return all tracked signals for display in a UI (debugging / transparency)."""
    conn = _connect()
    rows = conn.execute("""
        SELECT signal, language, accept_count, reject_count
        FROM   pref_signals
        ORDER  BY (accept_count + reject_count) DESC
    """).fetchall()
    conn.close()
    label_map = {name: label for name, _, label, _ in _SIGNALS}
    return [
        {
            "signal":   s,
            "language": lang,
            "label":    label_map.get(s, s),
            "accepts":  a,
            "rejects":  r,
            "net":      a - r,
        }
        for s, lang, a, r in rows
    ]


# ── Autonomous improvement suggestions (Milestone G) ──────────────────────────
_SUGGEST_THRESHOLD = 3   # net accepts before surfacing as a suggestion


def suggest_new_preference() -> dict | None:
    """
    Check for a signal that has crossed the suggestion threshold and
    hasn't been surfaced yet. Returns one suggestion at a time so the
    UI isn't flooded — call again after dismissal to see the next one.

    Returns {"signal": str, "language": str, "label": str} or None.
    """
    conn = _connect()
    rows = conn.execute("""
        SELECT signal, language, accept_count, reject_count
        FROM   pref_signals
        WHERE  suggested = 0
    """).fetchall()
    conn.close()

    label_map = {name: label for name, _, label, _ in _SIGNALS}

    for signal, language, accept, reject in rows:
        net = accept - reject
        if net >= _SUGGEST_THRESHOLD:
            return {
                "signal":   signal,
                "language": language,
                "label":    label_map.get(signal, signal),
                "net":      net,
            }
    return None


def mark_suggestion_seen(signal: str, language: str) -> None:
    """Mark a signal as already surfaced so it isn't suggested again."""
    conn = _connect()
    conn.execute(
        "UPDATE pref_signals SET suggested = 1 WHERE signal = ? AND language = ?",
        (signal, language),
    )
    conn.commit()
    conn.close()
