"""
tools/file_ops.py — Mini IDE Phase 1
Sandboxed file system operations.
All public functions expect callers to have already validated
that paths are within the workspace root (see safe_resolve in main.py).
"""
from pathlib import Path
from typing import Tuple
import shutil

# Directories / filenames to always skip in tree listing
_SKIP: frozenset[str] = frozenset({
    ".git", ".hg", ".svn",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "node_modules", ".pnp",
    ".venv", "venv", "env",
    "dist", "build", "out", ".next", ".nuxt", ".svelte-kit",
    ".DS_Store", "Thumbs.db",
    "*.egg-info",
})


# ── Tree ──────────────────────────────────────────────────────────────────────
def list_directory(path: Path, root: Path) -> dict:
    """
    Recursively build a JSON-serialisable file tree.
    Folders come before files; both are sorted case-insensitively.
    Generated/dependency folders in _SKIP are excluded. Hidden project files
    (for example .env, .github, and .vscode) remain visible and editable.
    """
    rel = path.relative_to(root)
    rel_str = str(rel).replace("\\", "/")
    if rel_str == ".":
        rel_str = ""  # root node gets empty-string path

    node: dict = {
        "name": path.name if rel_str else root.name,
        "path": rel_str,
        "type": "directory" if path.is_dir() else "file",
    }

    if path.is_dir():
        children = []
        try:
            entries = sorted(
                path.iterdir(),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )
            for entry in entries:
                if entry.name in _SKIP:
                    continue
                children.append(list_directory(entry, root))
        except PermissionError:
            pass  # skip dirs we can't read
        node["children"] = children

    return node


# ── Read ──────────────────────────────────────────────────────────────────────
def read_file(path: Path) -> Tuple[str, str]:
    """
    Read a file's text content, trying UTF-8 then latin-1 as fallback.
    Returns (content, encoding_used).
    Binary files get replacement characters rather than crashing.
    """
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return path.read_text(encoding=enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
    # Last resort — replace undecodable bytes
    return path.read_text(encoding="utf-8", errors="replace"), "utf-8"


# ── Write ─────────────────────────────────────────────────────────────────────
def write_file(path: Path, content: str) -> None:
    """Write text to a file, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ── Create ────────────────────────────────────────────────────────────────────
def create_file(path: Path, is_dir: bool = False) -> None:
    """Create an empty file (or directory)."""
    if is_dir:
        path.mkdir(parents=True, exist_ok=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()


# ── Delete ────────────────────────────────────────────────────────────────────
def delete_file(path: Path) -> None:
    """Delete a file or recursively delete a directory."""
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


# ── Rename / move ─────────────────────────────────────────────────────────────
def rename_path(old: Path, new: Path) -> None:
    """Rename or move a file / directory within the workspace."""
    new.parent.mkdir(parents=True, exist_ok=True)
    old.rename(new)
