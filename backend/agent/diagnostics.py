"""
agent/diagnostics.py — Mini IDE Milestone F

Detects when the agent is stuck rather than letting it silently burn
through retries: same error repeating, imports that don't actually
exist in the project, or a task that's failed the same way before.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

# Python stdlib module names — anything not here and not in requirements.txt
# is flagged as a possible hallucinated import.
_STDLIB = set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else set()


def _error_signature(stderr: str) -> str:
    """
    Reduce a traceback to a short signature for repeat-detection —
    the exception type + message, stripped of line numbers/memory addresses.
    """
    lines = [l.strip() for l in stderr.strip().splitlines() if l.strip()]
    if not lines:
        return ""
    last = lines[-1]
    # Strip anything that looks like a memory address or line number
    sig = re.sub(r"0x[0-9a-fA-F]+", "", last)
    sig = re.sub(r"line \d+", "line N", sig)
    return sig[:200]


def detect_loop(attempt_errors: list[str]) -> bool:
    """
    Given the stderr from each attempt in a Run & Fix session, return True
    if the same error signature has repeated — meaning the fix isn't working
    and a different strategy is needed rather than another blind retry.
    """
    if len(attempt_errors) < 2:
        return False
    signatures = [_error_signature(e) for e in attempt_errors if e.strip()]
    if len(signatures) < 2:
        return False
    return signatures[-1] == signatures[-2] and signatures[-1] != ""


def detect_hallucination(code: str, workspace_imports: set[str] | None = None) -> list[str]:
    """
    Parse Python code and flag imports that are neither stdlib nor present
    elsewhere in the workspace's known imports / requirements.txt — these
    are the most likely case of the model inventing a package that doesn't
    actually exist in this project.

    Returns a list of suspicious module names. Best-effort only — a
    correct-but-uncommon package will sometimes be flagged; this is meant
    as a hint, not a hard block.
    """
    workspace_imports = workspace_imports or set()
    suspicious: list[str] = []

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                found.add(node.module.split(".")[0])

    for mod in found:
        if mod in _STDLIB:
            continue
        if mod in workspace_imports:
            continue
        if mod.startswith("_"):
            continue
        suspicious.append(mod)

    return suspicious


def load_known_packages(workspace: Path) -> set[str]:
    """Read requirements.txt / package.json to build a known-package set."""
    known: set[str] = set()

    req = workspace / "requirements.txt"
    if req.exists():
        try:
            for line in req.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    name = re.split(r"[<>=\[!~]", line)[0].strip()
                    if name:
                        known.add(name.replace("-", "_"))
        except Exception:
            pass

    pkg = workspace / "package.json"
    if pkg.exists():
        try:
            import json
            data = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            known.update(deps.keys())
        except Exception:
            pass

    return known


def detect_repeated_failure(recent_tasks: list[dict], file_path: str, threshold: int = 3) -> bool:
    """
    Given recent journal entries (newest first) and a file path, return
    True if the last `threshold` tasks touching this file all failed.
    """
    matching = [t for t in recent_tasks if t.get("file_path") == file_path][:threshold]
    if len(matching) < threshold:
        return False
    return all(t.get("outcome") != "applied" for t in matching)


def suggest_alternate_model(current_model: str, available: list[str] | None = None) -> str:
    """
    Pick a different model than the one that's been failing.
    Simple heuristic: prefer a different model family from a small known list.
    Updated 2026-08-27 to available local models.
    """
    fallback_order = [
        "qwen3:8b",
        "qwen3:4b",
        "deepseek-coder:6.7b",
        "qwen2.5:1.5b",
        "artifish/llama3.2-uncensored:latest",
    ]
    candidates = available or fallback_order
    for m in candidates:
        if m != current_model:
            return m
    return current_model
