"""
rag/embedder.py — Mini IDE Phase 4

Async wrapper around Ollama's /api/embeddings endpoint.
Default model: nomic-embed-text (768-dimensional).
"""
import httpx

EMBED_MODEL = "nomic-embed-text"
EMBED_DIM   = 768
OLLAMA_BASE = "http://localhost:11434"
_TIMEOUT    = httpx.Timeout(connect=5.0, read=60.0, write=5.0, pool=5.0)


async def get_embedding(text: str, model: str = EMBED_MODEL) -> list[float] | None:
    """
    Return the embedding vector for the given text, or None on any error.
    Strips the text to avoid sending empty prompts.
    """
    text = text.strip()
    if not text:
        return None
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{OLLAMA_BASE}/api/embeddings",
                json={"model": model, "prompt": text},
            )
            r.raise_for_status()
            vec = r.json().get("embedding")
            if vec and len(vec) > 0:
                return vec
    except Exception:
        pass
    return None


async def check_embed_model(model: str = EMBED_MODEL) -> bool:
    """Return True if the embedding model is available in Ollama."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
            r = await client.get(f"{OLLAMA_BASE}/api/tags")
            r.raise_for_status()
            names = [m["name"] for m in r.json().get("models", [])]
            return any(model in n for n in names)
    except Exception:
        return False
