"""
memory/checkpoint.py — Mini IDE Milestone C

Lightweight, file-based snapshot system. Every AI write creates a
timestamped checkpoint under workspace/.checkpoints/. Independent of
the SQLite undo stack from Phase 6 — checkpoints are a full session
timeline per file, browsable and restorable at any point.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def _checkpoint_dir(file_path: str, workspace: Path) -> Path:
    """Map a relative file path to a safe checkpoint directory name."""
    safe = file_path.replace("\\", "/").replace("/", "__")
    d = workspace / ".checkpoints" / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


def create_checkpoint(
    file_path: str,
    content:   str,
    workspace: Path,
    label:     str = "",
) -> dict:
    """
    Save a snapshot of `content` for `file_path`.
    Returns {id, ts, label, size}.
    """
    d   = _checkpoint_dir(file_path, workspace)
    ts  = datetime.now()
    cid = ts.strftime("%Y%m%dT%H%M%S%f")

    (d / f"{cid}.bak").write_text(content, encoding="utf-8")
    meta = {"id": cid, "ts": ts.isoformat(), "label": label, "size": len(content)}
    (d / f"{cid}.json").write_text(json.dumps(meta), encoding="utf-8")
    return meta


def list_checkpoints(file_path: str, workspace: Path, limit: int = 30) -> list[dict]:
    """Return checkpoints for a file, newest first."""
    d = _checkpoint_dir(file_path, workspace)
    if not d.exists():
        return []
    metas = []
    for meta_file in sorted(d.glob("*.json"), reverse=True)[:limit]:
        try:
            metas.append(json.loads(meta_file.read_text(encoding="utf-8")))
        except Exception:
            continue
    return metas


def restore_checkpoint(file_path: str, checkpoint_id: str, workspace: Path) -> str | None:
    """Return the saved content for a checkpoint, or None if not found."""
    d    = _checkpoint_dir(file_path, workspace)
    bak  = d / f"{checkpoint_id}.bak"
    if not bak.exists():
        return None
    try:
        return bak.read_text(encoding="utf-8")
    except Exception:
        return None


def prune_old_checkpoints(file_path: str, workspace: Path, keep: int = 30) -> None:
    """Delete checkpoints beyond the most recent `keep`."""
    d = _checkpoint_dir(file_path, workspace)
    if not d.exists():
        return
    metas = sorted(d.glob("*.json"), reverse=True)
    for meta_file in metas[keep:]:
        cid = meta_file.stem
        (d / f"{cid}.bak").unlink(missing_ok=True)
        meta_file.unlink(missing_ok=True)
