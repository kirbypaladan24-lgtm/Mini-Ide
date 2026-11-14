"""
context_engine/workspace_state.py — Mini IDE Phase 3

Builds the rich workspace context that gets injected into LLM prompts.
Replaces the simple single-file injection from Phase 2.

Priority order (most → least important):
  1.  Current file          — always highest priority
  2.  Imported local deps   — auto-resolved via import_resolver
  3.  Other open tabs       — files the user has open
  4.  AST symbol summary    — injected as an HTML comment into the file block
  5.  Error log             — Phase 5, stub only for now
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from tools.file_ops import read_file
from tools.ast_parser import parse_symbols
from context_engine.import_resolver import resolve_imports
from context_engine.token_budget import TokenBudget


# ── Data model ────────────────────────────────────────────────────────────────
@dataclass
class FileEntry:
    path:    str
    content: str
    role:    str  # "current" | "import" | "tab"


@dataclass
class WorkspaceContext:
    current_file: FileEntry | None        = None
    symbols:      dict                    = field(default_factory=dict)
    imports:      list[FileEntry]         = field(default_factory=list)
    open_tabs:    list[FileEntry]         = field(default_factory=list)
    error_log:    str                     = ""

    # ── Format for LLM injection ──────────────────────────────────────────────
    def to_prompt_string(self) -> str:
        """
        Return a formatted string ready to be injected into the LLM message.
        Sections are separated by a rule so the model can distinguish them.
        """
        parts: list[str] = []

        if self.current_file:
            ext         = _ext(self.current_file.path)
            symbol_note = _symbol_comment(self.symbols)
            parts.append(
                f"### Current file: `{self.current_file.path}`{symbol_note}\n\n"
                f"```{ext}\n{self.current_file.content}\n```"
            )

        for imp in self.imports:
            ext = _ext(imp.path)
            parts.append(
                f"### Imported file: `{imp.path}`\n\n"
                f"```{ext}\n{imp.content}\n```"
            )

        for tab in self.open_tabs:
            ext = _ext(tab.path)
            parts.append(
                f"### Open tab: `{tab.path}`\n\n"
                f"```{ext}\n{tab.content}\n```"
            )

        if self.error_log:
            parts.append(
                f"### Recent errors:\n\n```\n{self.error_log}\n```"
            )

        return "\n\n---\n\n".join(parts)

    # ── Summary for the frontend context badge ────────────────────────────────
    def summary(self) -> dict:
        return {
            "current_file":  self.current_file.path if self.current_file else None,
            "imports":       [i.path for i in self.imports],
            "open_tabs":     [t.path for t in self.open_tabs],
            "symbols":       self.symbols,
        }


# ── Builder ───────────────────────────────────────────────────────────────────
def build_workspace_context(
    workspace:        Path,
    file_path:        str,
    file_content:     str,
    language:         str,
    open_tab_paths:   list[str],
    model:            str,
    include_imports:  bool = True,
    include_tabs:     bool = True,
) -> WorkspaceContext:
    """
    Assemble the full workspace context for the current active file.
    Applies the token budget so higher-priority layers are never dropped.
    """
    ctx    = WorkspaceContext()
    budget = TokenBudget(model)

    # ── 1. Current file (always first, always kept) ──────────────────────────
    trimmed = budget.trim(file_content, reserve=2_000)
    ctx.current_file = FileEntry(
        path    = file_path,
        content = trimmed,
        role    = "current",
    )
    budget.consume(trimmed)

    # ── 2. AST symbols ───────────────────────────────────────────────────────
    if language in ("python", "javascript", "typescript"):
        try:
            abs_path = (workspace / file_path).resolve()
            ctx.symbols = parse_symbols(abs_path, language)
        except Exception:
            ctx.symbols = {}

    # ── 3. Imported local dependencies ───────────────────────────────────────
    if include_imports and budget.remaining > 1_000:
        try:
            abs_path  = (workspace / file_path).resolve()
            resolved  = resolve_imports(abs_path, workspace, language)
            for dep in resolved:
                if budget.remaining < 500:
                    break
                content = budget.trim(dep["content"], max_chars=4_000)
                if content:
                    ctx.imports.append(
                        FileEntry(path=dep["path"], content=content, role="import")
                    )
                    budget.consume(content)
        except Exception:
            pass

    # ── 4. Other open tabs ───────────────────────────────────────────────────
    if include_tabs and budget.remaining > 400:
        for tab_path in open_tab_paths:
            if tab_path == file_path:
                continue
            if budget.remaining < 300:
                break
            try:
                abs_tab = (workspace / tab_path).resolve()
                if not abs_tab.exists():
                    continue
                content, _ = read_file(abs_tab)
                content = budget.trim(content, max_chars=2_000)
                if content:
                    ctx.open_tabs.append(
                        FileEntry(path=tab_path, content=content, role="tab")
                    )
                    budget.consume(content)
            except Exception:
                continue

    return ctx


# ── Helpers ───────────────────────────────────────────────────────────────────
def _ext(path: str) -> str:
    return Path(path).suffix.lstrip(".") or "text"


def _symbol_comment(symbols: dict) -> str:
    if not symbols:
        return ""
    parts: list[str] = []
    if symbols.get("functions"):
        fns = symbols["functions"][:8]
        parts.append(f"functions: {', '.join(fns)}")
    if symbols.get("classes"):
        cls = symbols["classes"]
        parts.append(f"classes: {', '.join(cls)}")
    if not parts:
        return ""
    return f"\n<!-- {' | '.join(parts)} -->"
