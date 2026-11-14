"""
context_engine/codebase_summary.py — Mini IDE Sprint 3

Builds and caches a compressed map of the entire workspace.
~2–3k tokens per summary — fits in any local model's context window.

Format:
  backend/main.py  (FastAPI app · 42 endpoints)
    set_workspace(payload: WorkspacePayload) → dict
    ws_chat(websocket: WebSocket) → async
    ...

  frontend/src/App.jsx  (IDE shell · 380 lines)
    App() → JSX
    handleApplyCode(path, newContent) → async

Injected into every LLM call so the AI knows the codebase structure
without the user having to manually include files.
"""
from __future__ import annotations

import ast
import re
import threading
import time
from pathlib import Path

_SKIP = frozenset({
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "dist", "build", ".next", ".uploads", ".rag_cache",
    ".checkpoints", ".idea", ".vscode",
})

_MAX_CHARS   = 12_000   # hard cap on summary length
_MAX_FNS     = 8        # max functions per file
_CACHE_TTL   = 30.0     # seconds before cache is considered stale

# ── Module-level cache ────────────────────────────────────────────────────────
_cache: dict = {}   # {"summary": str, "ts": float, "workspace": str}
_lock  = threading.Lock()


# ── Public API ────────────────────────────────────────────────────────────────
def get_summary(workspace: Path) -> str:
    """
    Return the cached summary for this workspace, rebuilding if stale.
    Threadsafe — can be called from any asyncio task via to_thread.
    """
    ws_str = str(workspace.resolve())
    with _lock:
        c = _cache.get("data")
        if c and c["workspace"] == ws_str and (time.monotonic() - c["ts"]) < _CACHE_TTL:
            return c["summary"]

    summary = build_summary(workspace)
    with _lock:
        _cache["data"] = {"workspace": ws_str, "ts": time.monotonic(), "summary": summary}
    return summary


def invalidate() -> None:
    """Force rebuild on the next get_summary() call."""
    with _lock:
        _cache.clear()


def build_summary(workspace: Path) -> str:
    """
    Walk the workspace and build a human+LLM readable file map.
    """
    sections: list[str] = [f"Workspace: {workspace.name}\n"]
    total_chars = len(sections[0])

    # Collect and sort files: Python first (most important for backend),
    # then JS/JSX (frontend), then everything else
    py_files  = _collect(workspace, "*.py")
    jsx_files = _collect(workspace, "*.jsx") + _collect(workspace, "*.tsx")
    ts_files  = _collect(workspace, "*.ts")
    js_files  = _collect(workspace, "*.js")
    other_key = _collect_other(workspace, {"*.yaml","*.yml","*.toml","*.cfg","*.md","requirements.txt","package.json"})

    all_groups = [
        ("Python", py_files),
        ("Frontend", jsx_files + ts_files + js_files),
        ("Config / Docs", other_key),
    ]

    for group_name, files in all_groups:
        if not files:
            continue
        header = f"\n── {group_name} ──\n"
        if total_chars + len(header) > _MAX_CHARS:
            break
        sections.append(header)
        total_chars += len(header)

        for path in files:
            if total_chars >= _MAX_CHARS:
                break
            entry = _describe_file(path, workspace)
            if not entry:
                continue
            if total_chars + len(entry) > _MAX_CHARS:
                break
            sections.append(entry)
            total_chars += len(entry)

    return "".join(sections)


# ── File describers ───────────────────────────────────────────────────────────
def _describe_file(path: Path, workspace: Path) -> str:
    try:
        rel  = str(path.resolve().relative_to(workspace.resolve())).replace("\\", "/")
        size = path.stat().st_size
        if size == 0 or size > 300_000:
            return ""
    except Exception:
        return ""

    ext  = path.suffix.lower()
    if ext == ".py":
        return _describe_python(path, rel)
    if ext in (".jsx", ".tsx", ".js", ".ts"):
        return _describe_js(path, rel)
    return _describe_generic(path, rel)


def _describe_python(path: Path, rel: str) -> str:
    try:
        src  = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src)
    except Exception:
        return f"  {rel}\n"

    lines   = src.count("\n")
    sigs: list[str] = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sigs.append(_py_fn_sig(node, prefix="  "))
        elif isinstance(node, ast.ClassDef):
            sigs.append(f"  class {node.name}")
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    sigs.append(_py_fn_sig(child, prefix="    "))
        if len(sigs) >= _MAX_FNS:
            sigs.append(f"  … ({lines} lines total)")
            break

    body = "\n".join(sigs[:_MAX_FNS + 1])
    return f"\n{rel}  ({lines} lines)\n{body}\n"


def _describe_js(path: Path, rel: str) -> str:
    try:
        src   = path.read_text(encoding="utf-8", errors="replace")
        lines = src.count("\n")
    except Exception:
        return f"  {rel}\n"

    # Extract exported function/component names via regex
    exports   = re.findall(r"export (?:default )?(?:function|const|class)\s+(\w+)", src)
    functions = re.findall(r"(?:^|\n)(?:async\s+)?function\s+(\w+)", src)
    arrows    = re.findall(r"(?:const|let)\s+(\w+)\s*=\s*(?:async\s*)?\(", src)

    names = list(dict.fromkeys(exports + functions + arrows))[:_MAX_FNS]
    body  = "\n".join(f"  {n}()" for n in names)
    extra = f"  … ({lines} lines total)" if len(names) >= _MAX_FNS else ""
    return f"\n{rel}  ({lines} lines)\n{body}{extra}\n"


def _describe_generic(path: Path, rel: str) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").count("\n")
        return f"\n{rel}  ({lines} lines)\n"
    except Exception:
        return f"\n{rel}\n"


# ── Helpers ───────────────────────────────────────────────────────────────────
def _py_fn_sig(node: ast.FunctionDef | ast.AsyncFunctionDef, prefix: str) -> str:
    args = []
    for a in node.args.args:
        if a.arg == "self":
            continue
        if a.annotation:
            try:
                args.append(f"{a.arg}: {ast.unparse(a.annotation)}")
            except Exception:
                args.append(a.arg)
        else:
            args.append(a.arg)
    ret = ""
    if node.returns:
        try:
            ret = f" → {ast.unparse(node.returns)}"
        except Exception:
            pass
    prefix_kw = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
    return f"{prefix}{prefix_kw}def {node.name}({', '.join(args[:4])}){ret}"


def _collect(workspace: Path, pattern: str) -> list[Path]:
    files = []
    for p in sorted(workspace.rglob(pattern)):
        if any(s in p.parts for s in _SKIP):
            continue
        try:
            files.append((p.stat().st_mtime, p))
        except Exception:
            continue
    files.sort(reverse=True)
    return [p for _, p in files]


def _collect_other(workspace: Path, patterns: set) -> list[Path]:
    found: list[Path] = []
    for pat in patterns:
        found.extend(_collect(workspace, pat))
    return found
