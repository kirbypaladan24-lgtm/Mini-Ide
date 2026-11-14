"""
llm/client.py — Mini IDE Phase 2
Async streaming client for the local Ollama server.
"""
import json
import httpx
from typing import AsyncGenerator

OLLAMA_BASE = "http://localhost:11434"

# Generous timeout: 5s to connect, 2min for long generations
_TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0)


async def stream_chat(
    model: str,
    messages: list[dict],
    temperature: float = 0.15,
    num_ctx: int = 4096,
) -> AsyncGenerator[str, None]:
    """
    Stream tokens from Ollama's /api/chat endpoint.

    Yields one string per token as they arrive.
    Raises httpx.ConnectError if Ollama is not running,
    httpx.HTTPStatusError if the model name is wrong / not pulled.
    """
    payload = {
        "model":   model,
        "messages": messages,
        "stream":  True,
        "options": {
            "temperature": temperature,
            "num_ctx":     num_ctx,
        },
    }

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        async with client.stream(
            "POST",
            f"{OLLAMA_BASE}/api/chat",
            json=payload,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                try:
                    data  = json.loads(line)
                    token = data.get("message", {}).get("content", "")
                    if token:
                        yield token
                    if data.get("done"):
                        return
                except json.JSONDecodeError:
                    continue


async def list_models() -> list[str]:
    """Return the names of all models pulled into Ollama."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
        r = await client.get(f"{OLLAMA_BASE}/api/tags")
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]


async def check_connection() -> bool:
    """Return True if the Ollama server is reachable."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(3.0)) as client:
            r = await client.get(f"{OLLAMA_BASE}/api/tags")
            return r.status_code == 200
    except Exception:
        return False
