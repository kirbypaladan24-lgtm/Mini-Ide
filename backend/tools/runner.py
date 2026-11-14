"""
tools/runner.py — Mini IDE Phase 5

Executes source files in a sandboxed subprocess capped to the workspace.
Uses sys.executable so the correct venv Python is always used.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

DEFAULT_TIMEOUT = 30   # seconds

# Command templates — {file} is replaced with the absolute path
_RUNNERS: dict[str, list[str]] = {
    "python":     [sys.executable, "{file}"],
    "javascript": ["node", "{file}"],
    "typescript": ["npx", "--yes", "ts-node", "{file}"],
    "shell":      ["bash", "{file}"],
    "bat":        ["{file}"],
    "go":         ["go", "run", "{file}"],
    "rust":       ["cargo", "run", "--manifest-path",
                   "{dir}/Cargo.toml"],  # best-effort for single-file rs
}

# Languages we advertise as runnable in the UI
RUNNABLE_LANGUAGES: frozenset[str] = frozenset(
    {"python", "javascript", "typescript", "shell", "bat", "go"}
)


async def run_file(
    file_path: str,
    workspace: Path,
    language:  str,
    timeout:   int = DEFAULT_TIMEOUT,
) -> dict:
    """
    Execute a workspace file.  Always sandboxed to workspace directory.
    Returns {stdout, stderr, returncode, success}.
    """
    abs_path = (workspace / file_path).resolve()

    if not abs_path.exists():
        return _err(f"File not found: {file_path}")

    # Sandbox check
    try:
        abs_path.relative_to(workspace.resolve())
    except ValueError:
        return _err("File is outside workspace — refusing to run.")

    template = _RUNNERS.get(language)
    if not template:
        return _err(f"No runner for language '{language}'. "
                    f"Supported: {', '.join(sorted(RUNNABLE_LANGUAGES))}")

    command = [
        part
        .replace("{file}", str(abs_path))
        .replace("{dir}",  str(abs_path.parent))
        for part in template
    ]

    return await _run(command, cwd=workspace, timeout=timeout)


async def run_command(
    command: list[str],
    cwd:     Path,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """Run an arbitrary command (for future shell-tool support)."""
    return await _run(command, cwd=cwd, timeout=timeout)


# ── Internal ──────────────────────────────────────────────────────────────────
async def _run(command: list[str], cwd: Path, timeout: int) -> dict:
    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out_b, err_b = await asyncio.wait_for(
                proc.communicate(), timeout=float(timeout)
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return _err(f"Process timed out after {timeout}s", rc=-1)

        rc = proc.returncode or 0
        return {
            "stdout":     out_b.decode("utf-8", errors="replace"),
            "stderr":     err_b.decode("utf-8", errors="replace"),
            "returncode": rc,
            "success":    rc == 0,
        }

    except FileNotFoundError:
        return _err(f"Interpreter not found: {command[0]}\n"
                    f"Make sure it is installed and on PATH.")
    except Exception as e:
        return _err(str(e))


def _err(msg: str, rc: int = -1) -> dict:
    return {"stdout": "", "stderr": msg, "returncode": rc, "success": False}
