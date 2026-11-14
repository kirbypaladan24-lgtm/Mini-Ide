"""
agent/pr_generator.py — Mini IDE Sprint 5

Generates a Markdown PR description from the current branch's diff
against main/master, plus recent commit messages for context.
Fail-open throughout — returns a helpful message if git/gitpython
isn't available or there's no diff to describe.
"""
from __future__ import annotations

from pathlib import Path

from llm.client import stream_chat

try:
    import git as _git
    GIT_OK = True
except ImportError:
    _git   = None   # type: ignore
    GIT_OK = False


_SYSTEM = """\
You are writing a pull request description from a git diff and commit history.

Output ONLY Markdown in this exact structure:

## Summary
One to two sentences: what does this change accomplish and why.

## Changes
- Bullet list of the meaningful changes, grouped by file or feature.
  Skip trivial changes (formatting, comments) unless that's the whole PR.

## Testing
One sentence on how this was or should be tested.

Keep it concise. Do not invent functionality not shown in the diff.
"""


def _repo(workspace: Path):
    if not GIT_OK:
        return None
    try:
        return _git.Repo(str(workspace), search_parent_directories=True)
    except Exception:
        return None


def _get_diff_and_commits(workspace: Path, base_branch: str = "") -> dict:
    """
    Return {"diff": str, "commits": list[str], "branch": str, "base": str}
    or {"error": str} if something went wrong.
    """
    repo = _repo(workspace)
    if repo is None:
        return {"error": "Not a git repository, or gitpython is not installed."}

    try:
        current_branch = repo.active_branch.name
    except Exception:
        return {"error": "Could not determine the current branch (detached HEAD?)."}

    # Auto-detect base branch if not specified
    base = base_branch
    if not base:
        for candidate in ("main", "master", "develop"):
            if candidate in [h.name for h in repo.heads] and candidate != current_branch:
                base = candidate
                break
    if not base:
        return {"error": "Could not auto-detect a base branch (tried main/master/develop)."}

    try:
        diff_text = repo.git.diff(f"{base}...{current_branch}", "--stat")
        full_diff = repo.git.diff(f"{base}...{current_branch}")
        commits   = repo.git.log(f"{base}..{current_branch}", "--pretty=format:%s")
    except Exception as e:
        return {"error": f"Git diff failed: {e}"}

    if not full_diff.strip():
        return {"error": f"No differences found between {current_branch} and {base}."}

    return {
        "diff":       full_diff[:6_000],
        "stat":       diff_text,
        "commits":    [c for c in commits.splitlines() if c.strip()],
        "branch":     current_branch,
        "base":       base,
    }


async def generate_pr_description(
    workspace:   Path,
    base_branch: str = "",
    model:       str = "qwen3:8b",
) -> dict:
    """
    Returns {"ok": bool, "description": str, "branch": str, "base": str}
    or {"ok": False, "error": str}.
    """
    info = _get_diff_and_commits(workspace, base_branch)
    if "error" in info:
        return {"ok": False, "error": info["error"]}

    commits_section = "\n".join(f"- {c}" for c in info["commits"][:15]) or "(no commit messages)"

    user_msg = (
        f"Branch: {info['branch']} → {info['base']}\n\n"
        f"Commit messages:\n{commits_section}\n\n"
        f"File summary:\n{info['stat']}\n\n"
        f"Diff:\n```diff\n{info['diff']}\n```\n\n"
        "Write the PR description now."
    )

    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",   "content": user_msg},
    ]

    full = ""
    try:
        async for token in stream_chat(model, messages, temperature=0.2, num_ctx=8192):
            full += token
    except Exception as e:
        return {"ok": False, "error": f"Generation failed: {e}"}

    return {
        "ok":          True,
        "description": full.strip(),
        "branch":      info["branch"],
        "base":        info["base"],
    }


def get_branch_info(workspace: Path) -> dict:
    """Quick sync check of current branch + whether there's anything to describe."""
    repo = _repo(workspace)
    if repo is None:
        return {"available": False}
    try:
        branch = repo.active_branch.name
        dirty  = repo.is_dirty()
        return {"available": True, "branch": branch, "dirty": dirty}
    except Exception:
        return {"available": False}
