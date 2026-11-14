"""
llm/vision.py — Mini IDE Sprint 1

Sends images to a vision model (llama3.2-vision:11b by default) and returns
a text description suited for the AI's context window.

Three modes:
  describe()     — general description of what's in the image
  read_error()   — specifically extracts error messages / stack traces
  analyze_ui()   — extracts layout, components, colors for vibe coding
  analyze_diagram() — reads architecture / ER / flow diagrams
"""
from __future__ import annotations

import base64
from pathlib import Path

import httpx

_OLLAMA_URL  = "http://localhost:11434"
_TIMEOUT     = httpx.Timeout(180.0)   # vision models are slower — give it more time
_DEFAULT_MODEL = "llama3.2-vision:11b"  # was llava:13b — updated to available model


# ── Core call ─────────────────────────────────────────────────────────────────
async def _ask_vision(
    image_b64: str,
    prompt:    str,
    model:     str = _DEFAULT_MODEL,
) -> str:
    """
    Send a base64-encoded image + prompt to Ollama's vision API.
    Returns the model's response text, or an error string.
    """
    payload = {
        "model":  model,
        "prompt": prompt,
        "images": [image_b64],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 800},
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(f"{_OLLAMA_URL}/api/generate", json=payload)
            r.raise_for_status()
            return r.json().get("response", "").strip()
    except httpx.ConnectError:
        return "(Vision model unavailable — make sure ollama serve is running and llama3.2-vision:11b is pulled)"
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return "(Vision model not found — run: ollama pull llama3.2-vision:11b)"
        return f"(Vision API error: {e})"
    except Exception as e:
        return f"(Vision error: {e})"


async def _load_image(source: str | bytes | Path) -> str | None:
    """Load image from path, bytes, or existing base64 string → base64."""
    if isinstance(source, str) and len(source) > 260:
        return source   # already base64
    if isinstance(source, Path):
        try:
            source = source.read_bytes()
        except Exception:
            return None
    if isinstance(source, bytes):
        return base64.b64encode(source).decode()
    return None


# ── Public API ────────────────────────────────────────────────────────────────
async def describe(
    image: str | bytes | Path,
    question: str = "",
    model: str = _DEFAULT_MODEL,
) -> str:
    """
    General-purpose image description.
    If question is provided, answers it directly.
    """
    b64 = await _load_image(image)
    if not b64:
        return "(Could not load image)"

    if question:
        prompt = (
            f"Look at this image carefully and answer this question: {question}\n\n"
            "Be specific and reference what you actually see."
        )
    else:
        prompt = (
            "Describe this image in detail. Include: what is shown, "
            "any text visible, layout and structure, colors and style. "
            "Be thorough but concise."
        )

    return await _ask_vision(b64, prompt, model)


async def read_error(
    image: str | bytes | Path,
    model: str = _DEFAULT_MODEL,
) -> str:
    """
    Extract error messages and stack traces from a screenshot.
    Optimized for terminal output, browser error pages, IDE error panels.
    """
    b64 = await _load_image(image)
    if not b64:
        return "(Could not load image)"

    prompt = (
        "This is a screenshot containing an error message or stack trace. "
        "Extract and reproduce the EXACT text of:\n"
        "1. The error type and message\n"
        "2. The full stack trace if visible\n"
        "3. Any file names and line numbers mentioned\n"
        "4. Any other diagnostic information shown\n\n"
        "Reproduce the text exactly as shown — do not paraphrase."
    )
    return await _ask_vision(b64, prompt, model)


async def analyze_ui(
    image: str | bytes | Path,
    model: str = _DEFAULT_MODEL,
) -> str:
    """
    Analyze a UI screenshot or design mockup for vibe coding.
    Returns a structured description suitable for code generation.
    """
    b64 = await _load_image(image)
    if not b64:
        return "(Could not load image)"

    prompt = (
        "Analyze this UI design or screenshot in detail for a developer who "
        "wants to recreate it in code. Describe:\n\n"
        "LAYOUT:\n"
        "- Overall structure (sidebar + main, header + content, grid, etc.)\n"
        "- How elements are positioned and spaced\n\n"
        "COMPONENTS:\n"
        "- List every distinct UI component visible (buttons, inputs, cards, nav items, etc.)\n"
        "- For each: its label/content, state (active/disabled/hover), and position\n\n"
        "VISUAL STYLE:\n"
        "- Background colors (use hex if visible, otherwise describe)\n"
        "- Text colors and font weights\n"
        "- Border colors and border radius\n"
        "- Shadow and elevation\n"
        "- Overall theme: dark/light, minimal/dense, rounded/sharp\n\n"
        "INTERACTIONS visible (hover states, selected states, badges, tooltips):\n\n"
        "Be specific and technical — this will be used to write React/CSS code."
    )
    return await _ask_vision(b64, prompt, model)


async def analyze_diagram(
    image: str | bytes | Path,
    model: str = _DEFAULT_MODEL,
) -> str:
    """
    Read architecture diagrams, ER diagrams, flow charts, or system diagrams.
    Returns structured text describing entities and relationships.
    """
    b64 = await _load_image(image)
    if not b64:
        return "(Could not load image)"

    prompt = (
        "This is a software diagram (architecture, flow, ER, or system design). "
        "Extract all information precisely:\n\n"
        "ENTITIES/COMPONENTS:\n"
        "- List every box, node, service, table, or component by name\n\n"
        "RELATIONSHIPS:\n"
        "- List every arrow or connection: FROM → TO (label if shown)\n"
        "- Note direction of arrows (one-way, bidirectional)\n\n"
        "GROUPINGS:\n"
        "- Note any containers, clusters, or groupings of components\n\n"
        "LABELS/ANNOTATIONS:\n"
        "- Extract all text labels verbatim\n\n"
        "This information will be used to implement this architecture in code."
    )
    return await _ask_vision(b64, prompt, model)


async def is_vision_available(model: str = _DEFAULT_MODEL) -> bool:
    """Check if the vision model is available via Ollama."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
            r = await client.get(f"{_OLLAMA_URL}/api/tags")
            if r.status_code != 200:
                return False
            models = [m["name"] for m in r.json().get("models", [])]
            return any(model.split(":")[0] in m for m in models)
    except Exception:
        return False


async def pick_vision_strategy(description_text: str) -> str:
    """
    Given a user message, determine which vision analysis mode to use.
    Returns: "error" | "ui" | "diagram" | "describe"
    """
    lower = description_text.lower()
    if any(w in lower for w in ("error", "bug", "crash", "exception", "traceback", "fix")):
        return "error"
    if any(w in lower for w in ("ui", "design", "layout", "component", "replicate", "build", "create", "vibe", "style", "look like")):
        return "ui"
    if any(w in lower for w in ("diagram", "architecture", "flow", "chart", "er diagram", "schema", "implement")):
        return "diagram"
    return "describe"
