"""
tools/patch_engine.py — Mini IDE Phase 6

Applies structured patches to workspace files.
Supports two levels of precision:
  - file_replace:     overwrite the full file (same as Phase 2 apply)
  - function_replace: replace a single function/class using AST (Python only)

Multi-file patches are applied atomically — if any patch fails,
all already-written files are rolled back to their originals.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional

from tools.file_ops import read_file, write_file


# ── Single-function patch (Python AST) ───────────────────────────────────────
def apply_function_patch(
    content:   str,
    func_name: str,
    new_code:  str,
    language:  str = "python",
) -> Optional[str]:
    """
    Replace a named function/class in `content` with `new_code`.
    Returns the updated file content, or None if the symbol was not found.
    """
    if language == "python":
        return _replace_python_symbol(content, func_name, new_code)
    # JS/TS: fall back to None (caller should use file_replace)
    return None


def _replace_python_symbol(content: str, name: str, new_code: str) -> Optional[str]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None

    lines = content.splitlines(keepends=True)

    # Search top-level nodes AND class bodies
    candidates: list[ast.AST] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == name:                    # type: ignore[attr-defined]
                candidates.append(node)

    if not candidates:
        return None

    # Use the first match (usually top-level)
    node     = candidates[0]
    start    = node.lineno - 1                       # type: ignore[attr-defined]
    end      = getattr(node, "end_lineno", start + 1)

    new_lines = new_code.splitlines(keepends=True)
    if new_lines and not new_lines[-1].endswith("\n"):
        new_lines[-1] += "\n"

    return "".join(lines[:start] + new_lines + lines[end:])


# ── Multi-file atomic patch ───────────────────────────────────────────────────
class PatchError(Exception):
    pass


def apply_patches(patches: list[dict], workspace: Path) -> dict:
    """
    Apply a list of patch dicts atomically.

    Each patch dict has:
      type: "file_replace" | "function_replace"
      path: relative workspace path
      --- file_replace ---
      content: new file content
      --- function_replace ---
      function: symbol name
      new_code: replacement source
      language: "python" | "javascript" (optional, default python)

    Returns:
      {"ok": True,  "applied": [path, ...]}
      {"ok": False, "applied": [...], "error": "...", "rolled_back": True}
    """
    # Snapshot originals for rollback
    originals: dict[str, str] = {}
    applied:   list[str]      = []

    try:
        for patch in patches:
            rel    = patch.get("path", "")
            target = _safe_target(rel, workspace)
            kind   = patch.get("type", "file_replace")

            # Read original once per file
            if rel not in originals:
                originals[rel] = _read_or_empty(target)

            if kind == "file_replace":
                write_file(target, patch["content"])
                applied.append(rel)

            elif kind == "function_replace":
                current = originals[rel]
                lang    = patch.get("language", "python")
                updated = apply_function_patch(
                    current, patch["function"], patch["new_code"], lang
                )
                if updated is None:
                    raise PatchError(
                        f"Symbol '{patch['function']}' not found in {rel}"
                    )
                write_file(target, updated)
                applied.append(rel)

            else:
                raise PatchError(f"Unknown patch type: '{kind}'")

        return {"ok": True, "applied": applied}

    except Exception as exc:
        # Rollback every file we already wrote
        for rel, original in originals.items():
            try:
                target = _safe_target(rel, workspace)
                if original:
                    write_file(target, original)
                elif target.exists():
                    target.unlink()
            except Exception:
                pass
        return {
            "ok":          False,
            "applied":     applied,
            "error":       str(exc),
            "rolled_back": True,
        }


# ── Helpers ───────────────────────────────────────────────────────────────────
def _safe_target(rel: str, workspace: Path) -> Path:
    clean  = rel.replace("\\", "/").lstrip("/")
    target = (workspace / clean).resolve()
    if not str(target).startswith(str(workspace.resolve())):
        raise PatchError(f"Path traversal: {rel}")
    return target


def _read_or_empty(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        content, _ = read_file(path)
        return content
    except Exception:
        return ""
