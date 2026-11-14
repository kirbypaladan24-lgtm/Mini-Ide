"""
rag/retriever.py — Mini IDE Phase 4, instrumented in Milestone F

Public search interface. Embeds the user's query and returns
the most relevant code chunks from the FAISS index.
"""
from rag.embedder import get_embedding
from rag.indexer  import search_vectors, is_ready

# Chunks below this score are too distant to be useful
_MIN_SCORE = 0.15

# Milestone F: lightweight in-memory hit-rate tracking for observability.
# Resets on backend restart — good enough for a live session dashboard.
_stats = {"queries": 0, "hits": 0}


def get_search_stats() -> dict:
    """Return RAG search hit-rate stats for the observability dashboard."""
    queries = _stats["queries"]
    hits    = _stats["hits"]
    rate    = round(100 * hits / queries, 1) if queries else 0.0
    return {"queries": queries, "hits": hits, "hit_rate": rate}


async def semantic_search(
    query:          str,
    k:              int = 5,
    exclude_paths:  set[str] | None = None,
) -> list[dict]:
    """
    Embed query and return top-k relevant chunks.

    Args:
        query:          Natural-language or code query string.
        k:              Maximum number of results.
        exclude_paths:  File paths to exclude (e.g. the current file, already
                        included via the context engine).
    Returns:
        List of chunk dicts with keys:
          file_path, chunk_type, name, content, start_line, end_line, score
    """
    if not is_ready():
        return []

    _stats["queries"] += 1

    vec = await get_embedding(query)
    if not vec:
        return []

    results = search_vectors(vec, k=k + (len(exclude_paths) if exclude_paths else 0))

    # Filter out excluded files and low-score results, then deduplicate
    seen:    set[str] = set()
    filtered: list[dict] = []

    for r in results:
        if r["score"] < _MIN_SCORE:
            continue
        fp = r.get("file_path", "")
        if exclude_paths and fp in exclude_paths:
            continue
        dedup_key = f"{fp}:{r.get('name','')}:{r.get('chunk_type','')}"
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        filtered.append(r)
        if len(filtered) >= k:
            break

    if filtered:
        _stats["hits"] += 1

    return filtered


def format_rag_context(results: list[dict]) -> str:
    """Format RAG results as a prompt section for the LLM."""
    if not results:
        return ""
    parts = []
    for r in results:
        from pathlib import Path
        ext   = Path(r["file_path"]).suffix.lstrip(".") or "text"
        label = (
            f"{r['chunk_type']} `{r['name']}`"
            if r.get("name") and r["name"] not in ("header",)
            else r["file_path"]
        )
        parts.append(
            f"### Relevant code — {label} from `{r['file_path']}` "
            f"(lines {r['start_line']}–{r['end_line']}, "
            f"score {r['score']:.2f})\n\n"
            f"```{ext}\n{r['content']}\n```"
        )
    return "\n\n".join(parts)
