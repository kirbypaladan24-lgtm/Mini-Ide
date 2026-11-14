"""
agent/surgical_editor.py — Mini IDE, VS Code-agent-style targeted edits

Modern AI coding agents (Cursor, Aider, Copilot Workspace) don't ask the
model to regenerate an entire file for a small change — they ask for
precise SEARCH/REPLACE blocks and apply them mechanically. This is
faster, cheaper, and dramatically safer: the model can't accidentally
drop unrelated code it "forgot" to include when rewriting everything.

Format the model must output:

<<<<<<< SEARCH
[exact existing code, copied verbatim]
=======
[the replacement code]
>>>>>>> REPLACE

Multiple blocks are allowed per response for multiple distinct changes
in the same file.

Fail-open by design: if a block can't be located (model mis-copied the
search text), that block is reported as failed rather than corrupting
the file — the caller decides whether to fall back to a full rewrite.
"""
from __future__ import annotations

import re

_BLOCK_RE = re.compile(
    r"<{3,}\s*SEARCH\s*\n(.*?\n)={3,}\s*\n(.*?\n)>{3,}\s*REPLACE",
    re.DOTALL,
)


def parse_edit_blocks(text: str) -> list[dict]:
    """Extract every SEARCH/REPLACE block from model output, in order."""
    blocks = []
    for m in _BLOCK_RE.finditer(text):
        search  = m.group(1).rstrip("\n")
        replace = m.group(2).rstrip("\n")
        blocks.append({"search": search, "replace": replace})
    return blocks


def has_valid_blocks(text: str) -> bool:
    return bool(_BLOCK_RE.search(text))


def _normalize(line_block: str) -> str:
    """Normalize trailing whitespace per line for fuzzy matching."""
    return "\n".join(line.rstrip() for line in line_block.split("\n"))


def apply_edit_blocks(original: str, blocks: list[dict]) -> dict:
    """
    Apply each SEARCH/REPLACE block against `original`, in order.

    Matching strategy per block:
      1. Exact substring match — if found exactly once, replace it.
      2. If found 0 times, retry with trailing-whitespace-normalized
         line-by-line matching (models sometimes drop trailing spaces).
      3. If found 2+ times, it's ambiguous — fail rather than guess.

    Returns:
      {"content": str, "applied": int, "failed": [{"search": str, "reason": str}]}
    """
    content = original
    applied = 0
    failed: list[dict] = []

    for block in blocks:
        search  = block["search"]
        replace = block["replace"]

        if not search.strip():
            failed.append({"search": "(empty)", "reason": "empty SEARCH block"})
            continue

        count = content.count(search)

        if count == 1:
            content = content.replace(search, replace, 1)
            applied += 1
            continue

        if count == 0:
            fuzzy_result = _try_fuzzy_match(content, search, replace)
            if fuzzy_result is not None:
                content = fuzzy_result
                applied += 1
            else:
                failed.append({
                    "search": search[:200],
                    "reason": "not found in file — model may have mis-copied the text",
                })
            continue

        # count >= 2: ambiguous, refuse to guess which occurrence was meant
        failed.append({
            "search": search[:200],
            "reason": f"found {count} times in file — ambiguous, needs more context",
        })

    return {"content": content, "applied": applied, "failed": failed}


def _try_fuzzy_match(content: str, search: str, replace: str) -> str | None:
    """
    Two fuzzy passes, each retried only if the previous found no
    unambiguous match:

      1. Trailing-whitespace-only normalization (catches stray spaces).
      2. Fully dedented comparison (catches indentation-level mistakes —
         the most common failure mode for smaller local models copying
         a snippet). When this matches, the replacement text is
         re-indented to the ACTUAL indentation found in the file rather
         than trusting whatever indentation the model guessed at, so a
         wrong-indent search block never produces wrong-indent output.

    Returns the updated content, or None if no unambiguous match found.
    """
    lines        = content.split("\n")
    search_lines = search.split("\n")
    n            = len(search_lines)

    # Pass 1: trailing-whitespace-only match, indentation preserved as-is
    norm_search = _normalize(search)
    matches = [
        i for i in range(len(lines) - n + 1)
        if _normalize("\n".join(lines[i:i + n])) == norm_search
    ]
    if len(matches) == 1:
        start = matches[0]
        new_lines = lines[:start] + replace.split("\n") + lines[start + n:]
        return "\n".join(new_lines)
    if len(matches) > 1:
        return None   # ambiguous even on relaxed matching — don't guess

    # Pass 2: fully dedented match, then re-indent the replacement to fit
    dedented_search = _dedent(search)
    matches = []
    for i in range(len(lines) - n + 1):
        window = "\n".join(lines[i:i + n])
        if _dedent(window) == dedented_search:
            matches.append(i)
            if len(matches) > 1:
                break

    if len(matches) != 1:
        return None

    start = matches[0]
    actual_indent = _leading_whitespace(lines[start])
    reindented    = _reindent(replace, actual_indent)
    new_lines     = lines[:start] + reindented.split("\n") + lines[start + n:]
    return "\n".join(new_lines)


def _leading_whitespace(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def _dedent(block: str) -> str:
    """Strip the common leading whitespace shared by all non-blank lines."""
    lines = block.split("\n")
    indents = [
        len(l) - len(l.lstrip()) for l in lines if l.strip()
    ]
    if not indents:
        return block
    common = min(indents)
    return "\n".join(l[common:] if l.strip() else l for l in lines)


def _reindent(block: str, target_indent: str) -> str:
    """
    Re-indent an already-dedented-relative block so its first line's
    indentation matches target_indent, preserving relative indentation
    of subsequent lines within the block.
    """
    lines = block.split("\n")
    if not lines:
        return block
    base = _leading_whitespace(lines[0])
    out  = []
    for l in lines:
        if not l.strip():
            out.append(l)
            continue
        if l.startswith(base):
            out.append(target_indent + l[len(base):])
        else:
            out.append(target_indent + l.lstrip())
    return "\n".join(out)


def strip_blocks_for_display(text: str) -> str:
    """
    Return the model's explanation text with SEARCH/REPLACE blocks
    removed — used to show "what the model said" separately from
    "what it changed" in the agent transparency UI.
    """
    return _BLOCK_RE.sub("", text).strip()


def summarize_blocks(blocks: list[dict]) -> str:
    """One-line human-readable summary of how many edits were made."""
    n = len(blocks)
    if n == 0:
        return "no changes"
    if n == 1:
        return "1 targeted edit"
    return f"{n} targeted edits"
