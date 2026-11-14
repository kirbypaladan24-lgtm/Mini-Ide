"""
tools/sandbox.py — Mini IDE Milestone F

Lightweight execution isolation without requiring Docker. Every AI-driven
run (the Run & Fix loop especially, since it re-executes code repeatedly
without a fresh user confirmation each time) goes through this instead
of a bare subprocess call.

Restrictions applied by default:
  - Environment variables stripped down to the bare minimum needed to run
    (PATH, SYSTEMROOT/HOME, etc.) — no API keys or secrets leak into the
    sandboxed process.
  - PYTHONPATH locked to the workspace root only.
  - Process is killed on timeout.

If Docker is detected on PATH, run_sandboxed() can optionally use a
`docker run --rm --network none` container instead for true OS-level
isolation. Off by default since most users won't have Docker installed;
detect_docker() lets the caller decide whether to offer it.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path

DEFAULT_TIMEOUT = 30

_RUNNERS: dict[str, list[str]] = {
    "python":     [sys.executable, "{file}"],
    "javascript": ["node", "{file}"],
    "typescript": ["npx", "--yes", "ts-node", "{file}"],
    "shell":      ["bash", "{file}"],
    "bat":        ["{file}"],
    "go":         ["go", "run", "{file}"],
}

# Minimal environment variables every platform needs to run anything at all
_KEEP_ENV_VARS = {
    "PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "TEMP", "TMP",
    "HOME", "USER", "USERNAME", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
    "PATHEXT", "COMSPEC", "PROCESSOR_ARCHITECTURE",
}


def detect_docker() -> bool:
    """Return True if `docker` is available on PATH."""
    return shutil.which("docker") is not None


def _restricted_env(workspace: Path) -> dict[str, str]:
    """Build a minimal environment — no leaked secrets, locked PYTHONPATH."""
    env = {k: v for k, v in os.environ.items() if k.upper() in _KEEP_ENV_VARS}
    env["PYTHONPATH"] = str(workspace.resolve())
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


async def run_sandboxed(
    file_path: str,
    workspace: Path,
    language:  str,
    timeout:   int = DEFAULT_TIMEOUT,
    use_docker: bool = False,
) -> dict:
    """
    Execute a workspace file under restricted conditions.
    Returns {stdout, stderr, returncode, success, sandboxed: "subprocess"|"docker"}.
    """
    abs_path = (workspace / file_path).resolve()

    if not abs_path.exists():
        return _err(f"File not found: {file_path}")
    try:
        abs_path.relative_to(workspace.resolve())
    except ValueError:
        return _err("File is outside workspace — refusing to run.")

    if use_docker and detect_docker() and language == "python":
        return await _run_docker(abs_path, workspace, timeout)

    template = _RUNNERS.get(language)
    if not template:
        return _err(f"No runner for language '{language}'.")

    command = [
        part.replace("{file}", str(abs_path)).replace("{dir}", str(abs_path.parent))
        for part in template
    ]

    return await _run_subprocess(command, workspace, timeout)


async def _run_subprocess(command: list[str], workspace: Path, timeout: int) -> dict:
    env = _restricted_env(workspace)
    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(workspace),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=float(timeout))
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return _err(f"Process timed out after {timeout}s — killed.", rc=-1)

        rc = proc.returncode or 0
        return {
            "stdout": out_b.decode("utf-8", errors="replace"),
            "stderr": err_b.decode("utf-8", errors="replace"),
            "returncode": rc, "success": rc == 0, "sandboxed": "subprocess",
        }
    except FileNotFoundError:
        return _err(f"Interpreter not found: {command[0]}")
    except Exception as e:
        return _err(str(e))


async def _run_docker(abs_path: Path, workspace: Path, timeout: int) -> dict:
    """Run inside a network-isolated Docker container, workspace mounted read-write."""
    rel = abs_path.relative_to(workspace.resolve())
    command = [
        "docker", "run", "--rm", "--network", "none",
        "-v", f"{workspace.resolve()}:/workspace",
        "-w", "/workspace",
        "python:3.12-slim", "python", str(rel).replace("\\", "/"),
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=float(timeout))
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return _err(f"Docker process timed out after {timeout}s — killed.", rc=-1)

        rc = proc.returncode or 0
        return {
            "stdout": out_b.decode("utf-8", errors="replace"),
            "stderr": err_b.decode("utf-8", errors="replace"),
            "returncode": rc, "success": rc == 0, "sandboxed": "docker",
        }
    except Exception as e:
        return _err(f"Docker execution failed: {e}")


def _err(msg: str, rc: int = -1) -> dict:
    return {"stdout": "", "stderr": msg, "returncode": rc, "success": False, "sandboxed": "subprocess"}
