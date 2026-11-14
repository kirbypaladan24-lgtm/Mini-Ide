"""
rag/indexer.py — Mini IDE Phase 4

Manages the FAISS index for the current workspace.
  - index_workspace()    full index build (runs as a background task)
  - index_file()         incremental single-file re-index
  - search_vectors()     raw vector search
  - get_status()         progress for the frontend
  - save() / load()      disk persistence
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import numpy as np

try:
    import faiss as _faiss
    FAISS_OK = True
except ImportError:
    _faiss   = None          # type: ignore
    FAISS_OK = False

from rag.chunker import chunk_file, INDEXABLE_EXTS, _SKIP
from rag.embedder import get_embedding, EMBED_DIM

# ── Cache location ────────────────────────────────────────────────────────────
_CACHE_ROOT = Path(__file__).parent.parent / ".rag_cache"

# ── Module-level index state ──────────────────────────────────────────────────
_index:    Optional[object] = None   # faiss.Index
_meta:     list[dict]       = []     # parallel list of chunk metadata
_workspace: Optional[Path]  = None
_status:   dict             = {
    "status": "idle",
    "total":  0,
    "done":   0,
    "error":  None,
    "faiss":  FAISS_OK,
}


def get_status() -> dict:
    return dict(_status)


def is_ready() -> bool:
    return _status["status"] == "ready" and _index is not None


# ── Build ─────────────────────────────────────────────────────────────────────
async def index_workspace(workspace: Path) -> None:
    """
    Full workspace index build.  Designed to run as asyncio.create_task().
    Saves the result to disk so it persists across restarts.
    """
    global _index, _meta, _workspace, _status
    _workspace = workspace

    if not FAISS_OK:
        _status = {
            "status": "error", "total": 0, "done": 0, "faiss": False,
            "error":  "faiss-cpu not installed — run: pip install faiss-cpu",
        }
        return

    # Try loading a cached index first
    if await _try_load_cache(workspace):
        return

    _status = {"status": "indexing", "total": 0, "done": 0, "error": None, "faiss": True}
    _index   = None
    _meta    = []

    files = _collect_files(workspace)
    _status["total"] = len(files)

    vectors: list[list[float]] = []
    metas:   list[dict]        = []

    for i, fp in enumerate(files):
        try:
            chunks = chunk_file(fp, workspace)
            for chunk in chunks:
                vec = await get_embedding(chunk.embed_text())
                if vec:
                    vectors.append(vec)
                    metas.append(asdict(chunk))
        except Exception:
            pass
        _status["done"] = i + 1
        await asyncio.sleep(0)   # yield to event loop between files

    if vectors:
        arr    = np.array(vectors, dtype=np.float32)
        _index = _faiss.IndexFlatL2(arr.shape[1])
        _index.add(arr)                              # type: ignore[union-attr]
        _meta  = metas
        _save_cache(workspace)

    _status["status"] = "ready"


async def index_file(path: Path, workspace: Path) -> None:
    """
    Incremental re-index of a single changed file.
    Removes old chunks for this file, then re-adds.
    """
    global _index, _meta
    if not FAISS_OK or _index is None:
        return

    rel = str(path.resolve().relative_to(workspace.resolve())).replace("\\", "/")

    # Collect indices of existing chunks belonging to this file
    keep_vecs:  list[list[float]] = []
    keep_metas: list[dict]        = []
    dim = EMBED_DIM

    total = _index.ntotal                           # type: ignore[union-attr]
    if total > 0:
        all_vecs = np.zeros((total, dim), dtype=np.float32)
        _index.reconstruct_n(0, total, all_vecs)    # type: ignore[union-attr]
        for i, m in enumerate(_meta):
            if m.get("file_path") != rel:
                keep_vecs.append(all_vecs[i].tolist())
                keep_metas.append(m)

    # Re-embed new chunks
    try:
        chunks = chunk_file(path, workspace)
        for chunk in chunks:
            vec = await get_embedding(chunk.embed_text())
            if vec:
                keep_vecs.append(vec)
                keep_metas.append(asdict(chunk))
    except Exception:
        pass

    # Rebuild index
    if keep_vecs:
        arr    = np.array(keep_vecs, dtype=np.float32)
        _index = _faiss.IndexFlatL2(arr.shape[1])
        _index.add(arr)                             # type: ignore[union-attr]
        _meta  = keep_metas
        _save_cache(workspace)


# ── Search ────────────────────────────────────────────────────────────────────
def search_vectors(query_vec: list[float], k: int = 5) -> list[dict]:
    """
    Return the k nearest chunks to query_vec.
    Results are sorted by descending score (higher = more relevant).
    """
    if not FAISS_OK or _index is None or _index.ntotal == 0:  # type: ignore[union-attr]
        return []

    k   = min(k, _index.ntotal)                               # type: ignore[union-attr]
    arr = np.array([query_vec], dtype=np.float32)
    distances, indices = _index.search(arr, k)                # type: ignore[union-attr]

    results = []
    for dist, idx in zip(distances[0], indices[0]):
        if idx < 0 or idx >= len(_meta):
            continue
        score = 1.0 / (1.0 + float(dist))
        results.append({**_meta[idx], "score": round(score, 4)})

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


# ── Persistence ───────────────────────────────────────────────────────────────
def _cache_dir(workspace: Path) -> Path:
    import hashlib
    h = hashlib.md5(str(workspace.resolve()).encode()).hexdigest()[:10]
    return _CACHE_ROOT / h


def _save_cache(workspace: Path) -> None:
    try:
        d = _cache_dir(workspace)
        d.mkdir(parents=True, exist_ok=True)
        _faiss.write_index(_index, str(d / "index.faiss"))    # type: ignore[union-attr]
        (d / "meta.json").write_text(json.dumps(_meta, ensure_ascii=False))
    except Exception:
        pass


async def _try_load_cache(workspace: Path) -> bool:
    global _index, _meta
    d = _cache_dir(workspace)
    fi, fm = d / "index.faiss", d / "meta.json"
    if not (fi.exists() and fm.exists()):
        return False
    try:
        _index = _faiss.read_index(str(fi))
        _meta  = json.loads(fm.read_text())
        _status["status"] = "ready"
        _status["total"]  = len(_meta)
        _status["done"]   = len(_meta)
        return True
    except Exception:
        return False


# ── Helpers ───────────────────────────────────────────────────────────────────
def _collect_files(workspace: Path) -> list[Path]:
    files = []
    for f in workspace.rglob("*"):
        if not f.is_file():
            continue
        if any(skip in f.parts for skip in _SKIP):
            continue
        if f.name.startswith("."):
            continue
        if f.suffix.lower() not in INDEXABLE_EXTS:
            continue
        try:
            if f.stat().st_size > 500_000:
                continue
        except OSError:
            continue
        files.append(f)
    return files
