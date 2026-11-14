"""
tools/ast_parser.py — Mini IDE Phase 3

Extracts structural symbols (functions, classes, imports) from source files.
Used by the context engine to build a symbol summary for the LLM.
Phase 6 will extend this to drive AST-aware patching.
"""
import ast
import re
from pathlib import Path


def parse_symbols(path: Path, language: str) -> dict:
    """
    Return {"functions": [...], "classes": [...], "imports": [...]}
    for the given source file.
    Returns empty lists on any parsing failure.
    """
    try:
        if language == "python":
            return _python(path)
        if language in ("javascript", "typescript"):
            return _js(path)
    except Exception:
        pass
    return {"functions": [], "classes": [], "imports": []}


# ── Python ────────────────────────────────────────────────────────────────────
def _python(path: Path) -> dict:
    source = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {"functions": [], "classes": [], "imports": []}

    functions: list[str] = []
    classes:   list[str] = []
    imports:   list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                name = alias.asname or alias.name
                imports.append(f"{mod}.{name}" if mod else name)

    return {
        "functions": _dedup(functions),
        "classes":   _dedup(classes),
        "imports":   _dedup(imports)[:25],
    }


# ── JavaScript / TypeScript (regex-based, no parser dep) ─────────────────────
_FN_PATTERNS = [
    re.compile(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)"),
    re.compile(r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\("),
    re.compile(r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\w+\s*=>"),
]
_CLASS_RE  = re.compile(r"(?:export\s+)?class\s+(\w+)")
_IMPORT_RE = re.compile(r"import\s+.*?\s+from\s+['\"]([^'\"]+)['\"]")


def _js(path: Path) -> dict:
    source = path.read_text(encoding="utf-8", errors="replace")

    functions: list[str] = []
    for pat in _FN_PATTERNS:
        functions.extend(pat.findall(source))

    return {
        "functions": _dedup(functions),
        "classes":   _dedup(_CLASS_RE.findall(source)),
        "imports":   _IMPORT_RE.findall(source)[:25],
    }


def _dedup(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out:  list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
