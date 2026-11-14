"""
agent/trust.py — Mini IDE Milestone G

Converts the quality pipeline's review dict into a single trust score
(0-100) with a checklist breakdown. Shown in the diff header and chat
review badge so the user has one number to glance at before approving.

Weighting is normalized over only the checks that actually ran — a
trivial docstring edit that only goes through `verify` can still hit
100% trust; it isn't penalized for skipping security/performance
agents that were never relevant to begin with.
"""
from __future__ import annotations

_WEIGHTS = {
    "verify":      25,
    "critic":      30,
    "security":    25,
    "performance": 20,
}


def compute_trust_score(review: dict) -> dict:
    """
    Returns:
      {
        "score": int (0-100),
        "checks": {
          "verified":    bool,
          "reviewed":    bool | None,   # None = critic didn't run
          "secure":      bool | None,   # None = security agent didn't run
          "performant":  bool | None,   # None = performance agent didn't run
        }
      }
    """
    agents_run = set(review.get("agents_run", []))
    checks: dict = {}
    earned  = 0
    possible = 0

    # verify always ran (it's the baseline check)
    verified = bool(review.get("verified", False))
    checks["verified"] = verified
    possible += _WEIGHTS["verify"]
    earned   += _WEIGHTS["verify"] if verified else 0

    if "critic" in agents_run:
        reviewed = review.get("ok", True) and len(review.get("issues", [])) == 0
        checks["reviewed"] = reviewed
        possible += _WEIGHTS["critic"]
        earned   += _WEIGHTS["critic"] if reviewed else 0
    else:
        checks["reviewed"] = None

    if "security" in agents_run:
        sec = review.get("security") or {}
        secure = sec.get("risk", "low") != "high"
        checks["secure"] = secure
        possible += _WEIGHTS["security"]
        earned   += _WEIGHTS["security"] if secure else 0
    else:
        checks["secure"] = None

    if "performance" in agents_run:
        perf = review.get("performance") or {}
        high_severity = any(f.get("severity") == "high" for f in perf.get("findings", []))
        performant = not high_severity
        checks["performant"] = performant
        possible += _WEIGHTS["performance"]
        earned   += _WEIGHTS["performance"] if performant else 0
    else:
        checks["performant"] = None

    score = round(100 * earned / possible) if possible else 0
    return {"score": score, "checks": checks}
