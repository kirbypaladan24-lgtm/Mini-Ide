"""
tools/differ.py — Mini IDE Phase 6

Generates unified diffs and change statistics.
Used by the /api/diff endpoint to power the DiffViewer in the frontend.
"""
import difflib


def unified_diff(original: str, updated: str, path: str = "file") -> str:
    """
    Return a unified diff string between original and updated.
    Returns an empty string if the contents are identical.
    """
    a = original.splitlines(keepends=True)
    b = updated.splitlines(keepends=True)

    # Ensure trailing newline so the last hunk closes cleanly
    if a and not a[-1].endswith("\n"):
        a[-1] += "\n"
    if b and not b[-1].endswith("\n"):
        b[-1] += "\n"

    return "".join(
        difflib.unified_diff(
            a, b,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        )
    )


def diff_stats(original: str, updated: str) -> dict:
    """
    Return line-level change counts.
    {"added": N, "removed": N, "net": N}
    """
    a = original.splitlines()
    b = updated.splitlines()

    added = removed = 0
    for tag, _, _, _, _ in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if tag in ("replace", "insert"):
            added   += 1
        if tag in ("replace", "delete"):
            removed += 1

    # More accurate: count individual added/removed lines
    added = removed = 0
    for line in difflib.ndiff(a, b):
        if line.startswith("+ "):
            added   += 1
        elif line.startswith("- "):
            removed += 1

    return {
        "added":   added,
        "removed": removed,
        "net":     len(b) - len(a),
    }
