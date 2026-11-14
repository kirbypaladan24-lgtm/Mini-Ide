"""
agent/test_runner.py — Mini IDE Milestone C

Closes the loop between writing code and verifying it:
  - find_test_file(): locate an existing test file for a module
  - run_regression(): run it and report pass/fail after an AI edit
  - build_test_prompt(): construct the "write tests for this file" request
  - suggest_test_path(): where a generated test file should live
"""
from __future__ import annotations

import re
from pathlib import Path

from tools.sandbox import run_sandboxed

_TEST_RUNNABLE = {"python", "javascript", "typescript"}


def find_test_file(file_path: str, workspace: Path) -> str | None:
    """
    Look for an existing test file matching `file_path`.
    Checks, in order:
      tests/test_{stem}.py        (Python convention)
      test_{stem}.py              (same directory)
      {stem}.test.js / .test.ts   (JS/TS convention)
      __tests__/{stem}.test.js
    Returns the relative path if found, else None.
    """
    p     = Path(file_path)
    stem  = p.stem
    ext   = p.suffix
    base_dir = p.parent

    candidates: list[Path] = []

    if ext == ".py":
        candidates += [
            Path("tests") / f"test_{stem}.py",
            base_dir / f"test_{stem}.py",
            base_dir / "tests" / f"test_{stem}.py",
        ]
    elif ext in (".js", ".jsx", ".ts", ".tsx"):
        candidates += [
            base_dir / f"{stem}.test{ext}",
            base_dir / "__tests__" / f"{stem}.test{ext}",
            Path("tests") / f"{stem}.test{ext}",
        ]

    for c in candidates:
        if (workspace / c).exists():
            return str(c).replace("\\", "/")

    return None


def suggest_test_path(file_path: str, workspace: Path) -> str:
    """Suggest a path for a newly generated test file."""
    p    = Path(file_path)
    stem = p.stem
    ext  = p.suffix

    if ext == ".py":
        if (workspace / "tests").is_dir():
            return f"tests/test_{stem}.py"
        return str(p.parent / f"test_{stem}.py").replace("\\", "/")

    if ext in (".js", ".jsx", ".ts", ".tsx"):
        return str(p.parent / f"{stem}.test{ext}").replace("\\", "/")

    return str(p.parent / f"test_{stem}{ext}").replace("\\", "/")


def is_test_file(file_path: str) -> bool:
    """Heuristic check: is this path itself a test file?"""
    name = Path(file_path).name.lower()
    return (
        name.startswith("test_")
        or ".test." in name
        or "/tests/" in file_path.replace("\\", "/").lower()
        or "__tests__" in file_path
    )


async def run_regression(
    file_path: str,
    language:  str,
    workspace: Path,
) -> dict | None:
    """
    If a test file exists for `file_path`, run it and return the result.
    Returns None if no test file is found or the language isn't runnable.
    Never raises — failures are reported in the result dict.
    """
    if is_test_file(file_path):
        return None   # don't regression-check a test file against itself

    if language not in _TEST_RUNNABLE:
        return None

    test_path = find_test_file(file_path, workspace)
    if not test_path:
        return None

    result = await run_sandboxed(test_path, workspace, language, timeout=20)
    summary = _summarize(result, language)

    return {
        "test_path": test_path,
        "success":   result["success"],
        "summary":   summary,
        "stdout":    result["stdout"][-1500:],
        "stderr":    result["stderr"][-1500:],
    }


def _summarize(result: dict, language: str) -> str:
    """Extract a one-line pass/fail summary from pytest/jest-style output."""
    text = result["stdout"] + result["stderr"]

    # pytest: "3 passed, 1 failed in 0.12s"
    m = re.search(r"(\d+ passed)(?:, (\d+ failed))?(?:, (\d+ error\w*))?", text)
    if m:
        parts = [g for g in m.groups() if g]
        return ", ".join(parts) if parts else ("✓ passed" if result["success"] else "✗ failed")

    # jest: "Tests: 1 failed, 4 passed, 5 total"
    m2 = re.search(r"Tests:\s*(.+)", text)
    if m2:
        return m2.group(1).strip()

    return "✓ passed" if result["success"] else "✗ failed"
