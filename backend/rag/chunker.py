"""
rag/chunker.py — Mini IDE Phase 4

Splits source files into semantically meaningful chunks for FAISS indexing.
  - Python  → one chunk per function/class + a file-header chunk
  - JS/TS   → one chunk per function/class (regex) + file-header
  - Others  → fixed-size line blocks with overlap
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

# Extensions we will index
INDEXABLE_EXTS: frozenset[str] = frozenset({
    ".py", ".pyw",
    ".js", ".jsx", ".mjs",
    ".ts", ".tsx",
    ".json",
    ".md", ".txt",
    ".yaml", ".yml", ".toml", ".ini",
    ".html", ".css", ".scss",
    ".rs", ".go", ".cpp", ".cc", ".c", ".h",
    ".java", ".kt", ".sql", ".sh", ".bat",
})

# Dirs to skip (mirrors file_ops._SKIP)
_SKIP: frozenset[str] = frozenset({
    ".git", "__pycache__", "node_modules", ".venv", "venv", "env",
    "dist", "build", ".next", ".nuxt", ".idea", ".vscode",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
})

BLOCK_SIZE    = 80   # lines per non-code chunk
BLOCK_OVERLAP = 15


@dataclass
class Chunk:
    file_path:  str    # relative to workspace root
    chunk_type: str    # "function" | "class" | "block" | "header"
    name:       str    # symbol name or "header" or "block:N"
    content:    str    # raw source text of this chunk
    start_line: int
    end_line:   int

    def embed_text(self) -> str:
        """Formatted text sent to the embedding model."""
        label = (
            f"# {self.chunk_type}: {self.name} in {self.file_path}"
            if self.name not in ("header", )
            else f"# file header: {self.file_path}"
        )
        return f"{label}\n\n{self.content}"


# ── Public entry point ────────────────────────────────────────────────────────
def chunk_file(path: Path, workspace: Path) -> list[Chunk]:
    """
    Split a source file into chunks suitable for FAISS embedding.
    Returns an empty list on any error.
    """
    try:
        rel  = str(path.resolve().relative_to(workspace.resolve())).replace("\\", "/")
        src  = path.read_text(encoding="utf-8", errors="replace")
        ext  = path.suffix.lower()

        if ext in (".py", ".pyw"):
            return _chunk_python(src, rel)
        if ext in (".js", ".jsx", ".ts", ".tsx", ".mjs"):
            return _chunk_js(src, rel)
        return _chunk_lines(src, rel)
    except Exception:
        return []


# ── Python ────────────────────────────────────────────────────────────────────
def _chunk_python(src: str, rel: str) -> list[Chunk]:
    lines  = src.splitlines()
    chunks: list[Chunk] = []

    # File header: docstring + imports (first 40 lines)
    header_end = min(40, len(lines))
    chunks.append(Chunk(
        file_path  = rel,
        chunk_type = "header",
        name       = "header",
        content    = "\n".join(lines[:header_end]),
        start_line = 1,
        end_line   = header_end,
    ))

    try:
        tree = ast.parse(src)
    except SyntaxError:
        return chunks + _chunk_lines(src, rel)

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            chunks.append(_py_node_chunk(node, lines, rel, "function"))

        elif isinstance(node, ast.ClassDef):
            # Class-level chunk (trimmed to first 60 lines of the class)
            chunks.append(_py_node_chunk(node, lines, rel, "class"))
            # Each method inside the class
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    chunks.append(_py_node_chunk(child, lines, rel, "function"))

    return chunks


def _py_node_chunk(
    node:  ast.AST,
    lines: list[str],
    rel:   str,
    kind:  str,
) -> Chunk:
    start = node.lineno - 1                          # type: ignore[attr-defined]
    end   = getattr(node, "end_lineno", start + 30)  # type: ignore[attr-defined]
    end   = min(end, len(lines))
    body  = "\n".join(lines[start:end])
    return Chunk(
        file_path  = rel,
        chunk_type = kind,
        name       = node.name,                      # type: ignore[attr-defined]
        content    = body,
        start_line = start + 1,
        end_line   = end,
    )


# ── JavaScript / TypeScript (regex) ──────────────────────────────────────────
_JS_FN_RE = re.compile(
    r"(?:export\s+)?(?:async\s+)?function\s+(\w+)|"
    r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(",
    re.MULTILINE,
)
_JS_CLS_RE = re.compile(r"(?:export\s+)?class\s+(\w+)", re.MULTILINE)


def _chunk_js(src: str, rel: str) -> list[Chunk]:
    lines  = src.splitlines()
    chunks: list[Chunk] = [
        Chunk(rel, "header", "header", "\n".join(lines[:40]), 1, min(40, len(lines)))
    ]

    for m in _JS_FN_RE.finditer(src):
        name  = m.group(1) or m.group(2)
        start = src.count("\n", 0, m.start())
        end   = min(start + 40, len(lines))
        chunks.append(Chunk(
            rel, "function", name,
            "\n".join(lines[start:end]),
            start + 1, end,
        ))

    for m in _JS_CLS_RE.finditer(src):
        start = src.count("\n", 0, m.start())
        end   = min(start + 60, len(lines))
        chunks.append(Chunk(
            rel, "class", m.group(1),
            "\n".join(lines[start:end]),
            start + 1, end,
        ))

    return chunks if len(chunks) > 1 else chunks + _chunk_lines(src, rel)


# ── Generic line-based chunking ───────────────────────────────────────────────
def _chunk_lines(src: str, rel: str) -> list[Chunk]:
    lines  = src.splitlines()
    chunks = []
    i, n   = 0, 0
    while i < len(lines):
        end = min(i + BLOCK_SIZE, len(lines))
        chunks.append(Chunk(
            rel, "block", f"block:{n}",
            "\n".join(lines[i:end]),
            i + 1, end,
        ))
        i += BLOCK_SIZE - BLOCK_OVERLAP
        n += 1
    return chunks
