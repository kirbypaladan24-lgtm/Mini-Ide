"""
tools/verifier.py — Mini IDE Milestone A

Runs a chain of static checks on AI-generated code *before* the diff
is shown to the user. If any check fails the coder gets a silent
auto-fix pass rather than surfacing broken code.

Chain:  syntax  →  AST parse  →  ruff lint (if installed)

All checks fail-open: if a tool is missing or errors out, that step
returns ok=True so the pipeline never hard-blocks the user.
"""
from __future__ import annotations

import ast
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


# ── Result type ───────────────────────────────────────────────────────────────
@dataclass
class VerifyResult:
    ok:       bool
    errors:   list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    step:     str       = ""        # which check produced this result

    def to_dict(self) -> dict:
        return {
            "ok":       self.ok,
            "errors":   self.errors,
            "warnings": self.warnings,
            "step":     self.step,
        }


_PASS = VerifyResult(ok=True)


# ── Syntax check ──────────────────────────────────────────────────────────────
def check_syntax(code: str, language: str) -> VerifyResult:
    """
    Check basic syntax.
      Python   → py_compile  (stdlib, always available)
      JS/TS    → `node --check` if node is on PATH
      Others   → pass-through
    """
    if language == "python":
        return _py_syntax(code)
    if language in ("javascript", "typescript"):
        return _node_syntax(code, language)
    return _PASS


def _py_syntax(code: str) -> VerifyResult:
    import py_compile
    with tempfile.NamedTemporaryFile(
        suffix=".py", mode="w", encoding="utf-8", delete=False
    ) as f:
        f.write(code)
        tmp = Path(f.name)
    try:
        py_compile.compile(str(tmp), doraise=True)
        return VerifyResult(ok=True, step="syntax")
    except py_compile.PyCompileError as e:
        return VerifyResult(ok=False, errors=[str(e)], step="syntax")
    finally:
        tmp.unlink(missing_ok=True)


def _node_syntax(code: str, language: str) -> VerifyResult:
    if not shutil.which("node"):
        return _PASS
    ext = ".ts" if language == "typescript" else ".js"
    with tempfile.NamedTemporaryFile(
        suffix=ext, mode="w", encoding="utf-8", delete=False
    ) as f:
        f.write(code)
        tmp = Path(f.name)
    try:
        r = subprocess.run(
            ["node", "--check", str(tmp)],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return VerifyResult(ok=True, step="syntax")
        return VerifyResult(ok=False, errors=[r.stderr.strip()], step="syntax")
    except Exception:
        return _PASS
    finally:
        tmp.unlink(missing_ok=True)


# ── AST parse ─────────────────────────────────────────────────────────────────
def check_ast(code: str, language: str) -> VerifyResult:
    """
    For Python: parse the AST to catch structural errors py_compile misses.
    """
    if language != "python":
        return _PASS
    try:
        ast.parse(code)
        return VerifyResult(ok=True, step="ast")
    except SyntaxError as e:
        return VerifyResult(
            ok=False,
            errors=[f"AST error at line {e.lineno}: {e.msg}"],
            step="ast",
        )


# ── Ruff lint ─────────────────────────────────────────────────────────────────
def check_lint(code: str, language: str) -> VerifyResult:
    """
    Run ruff if it's installed. Returns ok=True if ruff is absent.
    Only hard-fails on error-level issues (E codes), not style warnings.
    """
    if language != "python":
        return _PASS
    if not shutil.which("ruff"):
        return _PASS

    with tempfile.NamedTemporaryFile(
        suffix=".py", mode="w", encoding="utf-8", delete=False
    ) as f:
        f.write(code)
        tmp = Path(f.name)
    try:
        r = subprocess.run(
            ["ruff", "check", "--output-format=json", "--quiet", str(tmp)],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0:
            return VerifyResult(ok=True, step="lint")

        try:
            issues = json.loads(r.stdout or "[]")
        except json.JSONDecodeError:
            return _PASS

        errors   = [
            f"Line {i['location']['row']}: [{i.get('code','')}] {i['message']}"
            for i in issues if i.get("code", "").startswith("E")
        ]
        warnings = [
            f"Line {i['location']['row']}: [{i.get('code','')}] {i['message']}"
            for i in issues if not i.get("code", "").startswith("E")
        ]
        return VerifyResult(
            ok=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            step="lint",
        )
    except Exception:
        return _PASS
    finally:
        tmp.unlink(missing_ok=True)


# ── Full pipeline ─────────────────────────────────────────────────────────────
def run_pipeline(code: str, language: str) -> VerifyResult:
    """
    Run the full verification chain.
    Returns the first failure encountered, or a final ok result with
    any accumulated warnings from lint.
    """
    warnings: list[str] = []

    for fn in (check_syntax, check_ast, check_lint):
        result = fn(code, language)
        warnings.extend(result.warnings)
        if not result.ok:
            return VerifyResult(
                ok=False,
                errors=result.errors,
                warnings=warnings,
                step=result.step,
            )

    return VerifyResult(ok=True, warnings=warnings, step="all")
