"""
knowledge_graph/git_layer.py — Mini IDE Milestone B

Answers "why was this code written this way?" using git blame and
commit messages. Fail-open throughout: if git or gitpython is not
available, every function returns an empty result.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

try:
    import git as _git
    GIT_OK = True
except ImportError:
    _git   = None   # type: ignore
    GIT_OK = False


def _repo(workspace: Path) -> Optional[object]:
    """Open the git repo for the workspace, or return None."""
    if not GIT_OK:
        return None
    try:
        return _git.Repo(str(workspace), search_parent_directories=True)
    except Exception:
        return None


# ── Blame ─────────────────────────────────────────────────────────────────────
def blame_range(
    file_path: str,
    line_start: int,
    line_end:   int,
    workspace:  Path,
) -> list[dict]:
    """
    Return blame info for lines [line_start, line_end] of file_path.

    Each result dict: {line, author, email, date, commit_hash, message}
    """
    repo = _repo(workspace)
    if repo is None:
        return []
    try:
        abs_path = (workspace / file_path).resolve()
        blame    = repo.blame("HEAD", str(abs_path))
        results  = []
        current_line = 1
        for commit, lines in blame:
            for raw in lines:
                if line_start <= current_line <= line_end:
                    results.append({
                        "line":        current_line,
                        "author":      commit.author.name,
                        "email":       commit.author.email,
                        "date":        commit.authored_datetime.isoformat(),
                        "commit_hash": str(commit.hexsha)[:8],
                        "message":     commit.message.strip().splitlines()[0],
                    })
                current_line += 1
        return results
    except Exception:
        return []


# ── Commit history for a symbol ───────────────────────────────────────────────
def function_history(
    func_name:  str,
    file_path:  str,
    line_start: int,
    workspace:  Path,
    max_commits: int = 10,
) -> list[dict]:
    """
    Return the last `max_commits` commits that touched lines near `func_name`.

    Each result: {hash, author, date, message}
    """
    repo = _repo(workspace)
    if repo is None:
        return []
    try:
        abs_path = (workspace / file_path).resolve()
        # -L flag: history for a line range
        log = repo.git.log(
            f"-L{line_start},{line_start + 30}:{str(abs_path)}",
            "--no-patch",
            f"-{max_commits}",
            "--pretty=format:%H|%an|%aI|%s",
        )
        results = []
        for line in log.strip().splitlines():
            parts = line.split("|", 3)
            if len(parts) == 4:
                results.append({
                    "hash":    parts[0][:8],
                    "author":  parts[1],
                    "date":    parts[2],
                    "message": parts[3],
                })
        return results
    except Exception:
        return []


# ── Repo summary ──────────────────────────────────────────────────────────────
def repo_summary(workspace: Path) -> dict:
    """Return basic repo metadata, or {} if not a git repo."""
    repo = _repo(workspace)
    if repo is None:
        return {}
    try:
        branch = repo.active_branch.name
    except Exception:
        branch = "detached HEAD"
    try:
        last   = repo.head.commit
        return {
            "branch":      branch,
            "last_commit": str(last.hexsha)[:8],
            "last_author": last.author.name,
            "last_date":   last.authored_datetime.isoformat(),
            "last_msg":    last.message.strip().splitlines()[0],
        }
    except Exception:
        return {"branch": branch}
