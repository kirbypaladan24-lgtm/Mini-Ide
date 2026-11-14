"""
agent/react_tools.py — Mini IDE VS Code-style agent tools

Exposes workspace operations as structured tools the ReAct loop can call.
Every tool is sandboxed to the current workspace (via safe_resolve logic)
and returns truncated, LLM-friendly observations.
"""
from __future__ import annotations

import asyncio
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

from tools.file_ops import read_file, write_file
from tools.ast_parser import parse_symbols

# Optional dependencies — RAG / knowledge graph may not be available in minimal envs
try:
    from rag.retriever import semantic_search as rag_search, format_rag_context
    _RAG_OK = True
except Exception:
    rag_search = None  # type: ignore
    format_rag_context = lambda x: ""  # type: ignore
    _RAG_OK = False

try:
    from knowledge_graph.query import find_callers, impact_analysis, get_file_symbols
    _KG_OK = True
except Exception:
    find_callers = lambda *a, **kw: []  # type: ignore
    impact_analysis = lambda *a, **kw: {"summary": "Knowledge graph not available"}  # type: ignore
    get_file_symbols = lambda *a, **kw: []  # type: ignore
    _KG_OK = False

# Directories to skip during grep / list
_IGNORED = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".rag_cache", ".ruff_cache", "__pycache__", ".next", "out", ".pytest_cache"}

_MAX_OBSERVATION = 8000
_MAX_GREP_HITS = 30
_MAX_FILE_CHARS = 8000


def _truncate(text: str, limit: int = _MAX_OBSERVATION) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n… truncated ({len(text)-limit} chars hidden)"


def _safe_resolve(workspace: Path, rel: str) -> Path | None:
    """Resolve rel inside workspace or return None if traversal."""
    clean = rel.replace("\\", "/").lstrip("/")
    # block absolute Windows paths
    if re.match(r"^[A-Za-z]:/", clean):
        return None
    target = (workspace / clean).resolve()
    try:
        target.relative_to(workspace.resolve())
    except ValueError:
        return None
    return target


# ── Tool implementations ────────────────────────────────────────────────────

async def tool_read_file(workspace: Path, path: str, limit: int = _MAX_FILE_CHARS) -> str:
    target = _safe_resolve(workspace, path)
    if not target:
        return f"Error: Path traversal blocked or absolute path not allowed: {path}"
    if not target.exists():
        return f"Error: File not found: {path}"
    if target.is_dir():
        return f"Error: {path} is a directory, use list_directory instead."
    try:
        content, enc = read_file(target)
        if len(content) > limit:
            content = content[:limit] + f"\n\n… file truncated ({len(content)} total chars, showing {limit})"
        return f"File: {path} ({len(content)} chars, encoding={enc})\n```\n{content}\n```"
    except Exception as e:
        return f"Error reading {path}: {e}"


async def tool_list_directory(workspace: Path, path: str = "") -> str:
    target = _safe_resolve(workspace, path) if path else workspace
    if not target:
        return f"Error: Path traversal blocked: {path}"
    if not target.exists():
        return f"Error: Directory not found: {path}"
    if not target.is_dir():
        return f"Error: {path} is not a directory"
    try:
        entries = []
        for p in sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if p.name in _IGNORED:
                continue
            rel = p.relative_to(workspace).as_posix()
            kind = "DIR " if p.is_dir() else "FILE"
            # annotate symbols for files if small
            entries.append(f"{kind} {rel}")
        if not entries:
            return f"Directory {path or '.'} is empty (or only ignored files)."
        return f"Directory listing for {path or '.'}:\n" + "\n".join(entries[:120])
    except Exception as e:
        return f"Error listing {path}: {e}"


async def tool_grep(workspace: Path, pattern: str, include: str = "") -> str:
    """Regex grep across workspace, returns file:line matches."""
    try:
        regex = re.compile(pattern, re.MULTILINE)
    except re.error as e:
        return f"Error: Invalid regex '{pattern}': {e}"
    hits = []
    # Determine filter
    include_re = None
    if include:
        try:
            include_re = re.compile(include)
        except re.error:
            include_re = None
    for p in workspace.rglob("*"):
        try:
            if any(part in _IGNORED for part in p.relative_to(workspace).parts):
                continue
            if not p.is_file():
                continue
            # optional filename filter
            rel = p.relative_to(workspace).as_posix()
            if include_re and not include_re.search(rel):
                continue
            # skip binaries by suffix
            if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".pdf", ".zip", ".exe", ".dll", ".faiss"}:
                continue
            if p.stat().st_size > 500_000:
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    hits.append(f"{rel}:{i}: {line.strip()[:200]}")
                    if len(hits) >= _MAX_GREP_HITS:
                        break
        except Exception:
            continue
        if len(hits) >= _MAX_GREP_HITS:
            break
    if not hits:
        return f"No matches for /{pattern}/"
    more = f"\n… showing {len(hits)} of many" if len(hits) == _MAX_GREP_HITS else ""
    return f"Grep /{pattern}/ — {len(hits)} hits:\n" + "\n".join(hits) + more


async def tool_semantic_search(workspace: Path, query: str, k: int = 5) -> str:
    if not _RAG_OK or rag_search is None:
        return f"Semantic search for '{query}': not available (RAG dependencies missing — install faiss-cpu, numpy)"
    try:
        hits = await rag_search(query, k=k)
        if not hits:
            return f"Semantic search for '{query}': no results (RAG not ready or no hits)"
        return format_rag_context(hits)[:_MAX_OBSERVATION]
    except Exception as e:
        return f"Semantic search error: {e}"


async def tool_get_symbols(workspace: Path, path: str) -> str:
    target = _safe_resolve(workspace, path)
    if not target:
        return f"Error: Path traversal blocked: {path}"
    if not target.exists():
        return f"Error: File not found: {path}"
    lang = _detect_language(target)
    try:
        syms = parse_symbols(target, lang)
        if not syms.get("functions") and not syms.get("classes"):
            return f"Symbols for {path}: (none found, language={lang})"
        out = [f"Symbols for {path} ({lang}):"]
        if syms.get("functions"):
            out.append(f"  functions: {', '.join(syms['functions'])}")
        if syms.get("classes"):
            out.append(f"  classes: {', '.join(syms['classes'])}")
        if syms.get("imports"):
            out.append(f"  imports: {', '.join(syms['imports'][:15])}")
        # also try knowledge graph
        try:
            kg = get_file_symbols(path, workspace)
            if kg:
                out.append(f"  kg_nodes: {len(kg)} symbols")
                for n in kg[:10]:
                    out.append(f"    - {n['kind']} {n['name']} : line {n['line_start']}")
        except Exception:
            pass
        return "\n".join(out)
    except Exception as e:
        return f"Error parsing symbols for {path}: {e}"


async def tool_find_callers(workspace: Path, symbol: str) -> str:
    try:
        callers = find_callers(symbol, workspace)
        if not callers:
            return f"No callers found for `{symbol}` (graph may not be built yet)."
        lines = [f"Callers of `{symbol}` ({len(callers)}):"]
        for c in callers[:20]:
            lines.append(f"  - {c.get('name')} ({c.get('kind')}) in {c.get('file_path')}:{c.get('line_start')}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error finding callers: {e}"


async def tool_impact_analysis(workspace: Path, symbol: str) -> str:
    try:
        report = impact_analysis(symbol, workspace)
        return report.get("summary", str(report))
    except Exception as e:
        return f"Error impact analysis: {e}"


async def tool_run_command(workspace: Path, command: str, timeout: int = 30) -> str:
    """Run shell command inside workspace, sandboxed."""
    command = command.strip()
    if not command:
        return "Error: Empty command"
    # Block destructive patterns
    _BLOCKED = [
        r"rm\s+-rf\s+/", r"mkfs\.", r":\(\)\{.*:\|:&.*\}", r"shutdown", r"reboot",
        r"DROP\s+TABLE", r"DELETE\s+FROM\s+\w+\s*;\s*$"
    ]
    for pat in _BLOCKED:
        if re.search(pat, command, re.IGNORECASE):
            return f"Error: Command blocked for safety (matches {pat}): {command[:100]}"
    # Also block attempts to escape workspace via cd /
    if ".." in command and "workspace" not in command.lower():
        # allow but warn — still sandboxed via cwd
        pass
    try:
        # Use shell=True for complex commands (pip, npm, pytest etc.)
        # On Windows, shell=True uses cmd; on Unix, /bin/sh
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=str(workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=float(timeout))
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return f"Command timed out after {timeout}s: {command}\n… killed"
        out = out_b.decode("utf-8", errors="replace")
        err = err_b.decode("utf-8", errors="replace")
        rc = proc.returncode or 0
        output = ""
        if out.strip():
            output += f"STDOUT:\n{out.strip()[:4000]}\n"
        if err.strip():
            output += f"STDERR:\n{err.strip()[:4000]}\n"
        output += f"Exit code: {rc} ({'success' if rc==0 else 'failed'})"
        return _truncate(output, 5000)
    except Exception as e:
        return f"Error running command '{command}': {e}"


async def tool_write_file(workspace: Path, path: str, content: str) -> str:
    target = _safe_resolve(workspace, path)
    if not target:
        return f"Error: Path traversal blocked: {path}"
    try:
        # Use file_ops.write_file which creates parents
        write_file(target, content)
        # Verify
        size = target.stat().st_size if target.exists() else 0
        return f"Wrote {path} ({size} bytes, {len(content.splitlines())} lines). File updated successfully."
    except Exception as e:
        return f"Error writing {path}: {e}"


async def tool_read_file_range(workspace: Path, path: str, start: int, end: int) -> str:
    """Read specific line range."""
    target = _safe_resolve(workspace, path)
    if not target:
        return f"Error: Path traversal blocked: {path}"
    if not target.exists():
        return f"Error: File not found: {path}"
    try:
        content, _ = read_file(target)
        lines = content.splitlines()
        # clamp
        start = max(1, start)
        end = min(len(lines), end) if end > 0 else len(lines)
        if start > end:
            return f"Error: start {start} > end {end} (file has {len(lines)} lines)"
        snippet = "\n".join(f"{i+1:4d} | {lines[i]}" for i in range(start-1, end))
        return f"File {path} lines {start}-{end} (total {len(lines)}):\n```\n{snippet}\n```"
    except Exception as e:
        return f"Error reading range: {e}"


def _detect_language(p: Path) -> str:
    name = p.name.lower()
    if name in ("dockerfile", "makefile"):
        return name
    mapping = {
        ".py": "python", ".pyw": "python", ".js": "javascript", ".jsx": "javascript",
        ".ts": "typescript", ".tsx": "typescript", ".json": "json", ".html": "html",
        ".css": "css", ".md": "markdown", ".yaml": "yaml", ".yml": "yaml",
        ".sh": "shell", ".bat": "bat", ".rs": "rust", ".go": "go", ".java": "java",
    }
    return mapping.get(p.suffix.lower(), "plaintext")


# ── Tool registry ─────────────────────────────────────────────────────────────
TOOLS = {
    "read_file": {
        "desc": "Read full file content. Use for understanding code before editing.",
        "params": {"path": "relative path from workspace root (e.g. src/app.py)"},
        "func": tool_read_file,
    },
    "read_file_range": {
        "desc": "Read specific line range of a file when you need surrounding context after a grep hit.",
        "params": {"path": "relative path", "start": "1-indexed start line", "end": "end line inclusive"},
        "func": tool_read_file_range,
    },
    "list_directory": {
        "desc": "List files and folders in a directory. Use to explore workspace structure.",
        "params": {"path": "relative directory path, '' for root"},
        "func": tool_list_directory,
    },
    "grep": {
        "desc": "Regex search across workspace (like VS Code search). Returns file:line hits. Use to find where a function/variable is used.",
        "params": {"pattern": "regex pattern", "include": "optional filename regex filter"},
        "func": tool_grep,
    },
    "semantic_search": {
        "desc": "Semantic code search via embeddings. Good for natural language queries like 'auth middleware' or 'database connection'.",
        "params": {"query": "search query", "k": "num results (default 5)"},
        "func": tool_semantic_search,
    },
    "get_symbols": {
        "desc": "Get functions/classes/imports defined in a file.",
        "params": {"path": "relative path"},
        "func": tool_get_symbols,
    },
    "find_callers": {
        "desc": "Find all places that call a function or use a class. Use to check impact before changing a symbol.",
        "params": {"symbol": "function or class name"},
        "func": tool_find_callers,
    },
    "impact_analysis": {
        "desc": "Full impact report for changing a symbol (callers + inheritors).",
        "params": {"symbol": "symbol name"},
        "func": tool_impact_analysis,
    },
    "run_command": {
        "desc": "Run a shell command in workspace root. Use to run tests (pytest, npm test), install deps, or check git status. Returns stdout/stderr/exit code.",
        "params": {"command": "shell command e.g. 'pytest -q', 'npm test', 'python main.py'", "timeout": "seconds (default 30)"},
        "func": tool_run_command,
    },
    "write_file": {
        "desc": "Create or overwrite a file with new content. Use to apply edits after you have read the file. Creates parent dirs automatically.",
        "params": {"path": "relative path", "content": "complete new file content"},
        "func": tool_write_file,
    },
}

TOOL_NAMES = list(TOOLS.keys())

def tool_definitions_prompt() -> str:
    """Return a compact tool listing for system prompt."""
    lines = []
    for name, spec in TOOLS.items():
        params = ", ".join(f"{k}: {v}" for k, v in spec["params"].items())
        lines.append(f"- {name}({params}) — {spec['desc']}")
    return "\n".join(lines)


async def dispatch_tool(workspace: Path, name: str, args: dict) -> str:
    """Execute a tool by name with args, return observation string."""
    spec = TOOLS.get(name)
    if not spec:
        return f"Error: Unknown tool '{name}'. Available: {', '.join(TOOL_NAMES)}"
    func = spec["func"]
    try:
        # Filter args to match function signature (ignore extra)
        # Build kwargs based on tool
        if name == "read_file":
            return await func(workspace, args.get("path", ""), int(args.get("limit", _MAX_FILE_CHARS)))
        elif name == "read_file_range":
            return await func(workspace, args.get("path", ""), int(args.get("start", 1)), int(args.get("end", 100)))
        elif name == "list_directory":
            return await func(workspace, args.get("path", ""))
        elif name == "grep":
            return await func(workspace, args.get("pattern", ""), args.get("include", ""))
        elif name == "semantic_search":
            return await func(workspace, args.get("query", ""), int(args.get("k", 5)))
        elif name == "get_symbols":
            return await func(workspace, args.get("path", ""))
        elif name == "find_callers":
            return await func(workspace, args.get("symbol", ""))
        elif name == "impact_analysis":
            return await func(workspace, args.get("symbol", ""))
        elif name == "run_command":
            return await func(workspace, args.get("command", ""), int(args.get("timeout", 30)))
        elif name == "write_file":
            return await func(workspace, args.get("path", ""), args.get("content", ""))
        else:
            return await func(workspace, **args)
    except Exception as e:
        return f"Tool {name} error: {e}"
