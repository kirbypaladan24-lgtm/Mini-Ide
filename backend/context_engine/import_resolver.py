"""
context_engine/import_resolver.py — Mini IDE Phase 3

Resolves local import dependencies so the context engine can include
relevant files automatically. Only workspace-local files are included;
stdlib and third-party packages are skipped.
"""
import ast
import re
from pathlib import Path

from tools.file_ops import read_file

MAX_CHARS_PER_DEP = 5_000   # cap each dependency to keep context manageable


def resolve_imports(
    file_path: Path,
    workspace: Path,
    language:  str,
) -> list[dict]:
    """
    Return [{path, content}] for local files imported by file_path.
    Returns an empty list on any error.
    """
    try:
        if language == "python":
            return _resolve_python(file_path, workspace)
        if language in ("javascript", "typescript"):
            return _resolve_js(file_path, workspace)
    except Exception:
        pass
    return []


# ── Python ────────────────────────────────────────────────────────────────────
def _resolve_python(file_path: Path, workspace: Path) -> list[dict]:
    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
        tree   = ast.parse(source)
    except Exception:
        return []

    module_names: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_names.append(alias.name.split(".")[0])

        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                # Absolute import — take the top-level package name
                module_names.append(node.module.split(".")[0])
            elif node.level > 0:
                # Relative import — resolve from current directory
                base = file_path.parent
                for _ in range(node.level - 1):
                    base = base.parent
                mod  = node.module or ""
                candidates = (
                    [(base / f"{mod.replace('.', '/')}.py"),
                     (base / mod / "__init__.py")]
                    if mod else
                    [(base / "__init__.py")]
                )
                for c in candidates:
                    if c.exists() and c != file_path and _in_ws(c, workspace):
                        result = _read_dep(c, workspace)
                        if result:
                            return [result]  # one relative import is enough
                continue

    # Look up module names as local .py files
    results: list[dict] = []
    seen = {file_path.resolve()}

    for mod in _unique(module_names):
        candidates = [
            workspace / f"{mod}.py",
            workspace / mod / "__init__.py",
            file_path.parent / f"{mod}.py",
        ]
        for c in candidates:
            resolved = c.resolve()
            if c.exists() and resolved not in seen and _in_ws(c, workspace):
                dep = _read_dep(c, workspace)
                if dep:
                    results.append(dep)
                    seen.add(resolved)
                break

    return results


# ── JavaScript / TypeScript ───────────────────────────────────────────────────
_JS_IMPORT_RE = re.compile(
    r"""(?:import\s+.*?\s+from\s+|require\s*\(\s*)['"](\.[^'"]+)['"]""",
    re.MULTILINE,
)
_JS_EXTS = (".js", ".jsx", ".ts", ".tsx", ".json")


def _resolve_js(file_path: Path, workspace: Path) -> list[dict]:
    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    results: list[dict] = []
    seen = {file_path.resolve()}
    base = file_path.parent

    for m in _JS_IMPORT_RE.finditer(source):
        raw  = m.group(1)
        stem = Path(raw)
        candidates = [
            *([(base / stem).with_suffix(ext) for ext in _JS_EXTS]),
            *([(base / stem / f"index{ext}") for ext in _JS_EXTS]),
        ]
        for c in candidates:
            try:
                rc = c.resolve()
            except Exception:
                continue
            if c.exists() and rc not in seen and _in_ws(c, workspace):
                dep = _read_dep(c, workspace)
                if dep:
                    results.append(dep)
                    seen.add(rc)
                break

    return results


# ── Helpers ───────────────────────────────────────────────────────────────────
def _in_ws(path: Path, workspace: Path) -> bool:
    try:
        path.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


def _rel(path: Path, workspace: Path) -> str:
    return str(path.resolve().relative_to(workspace.resolve())).replace("\\", "/")


def _read_dep(path: Path, workspace: Path) -> dict | None:
    try:
        content, _ = read_file(path)
        return {
            "path":    _rel(path, workspace),
            "content": content[:MAX_CHARS_PER_DEP],
        }
    except Exception:
        return None


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out:  list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
