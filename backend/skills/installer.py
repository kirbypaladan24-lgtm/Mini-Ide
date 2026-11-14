"""
skills/installer.py — Mini IDE Milestone B

Downloads a .skill.yaml from a URL, validates it, saves it to the
installed/ directory, and registers it with the SkillManager.
"""
from __future__ import annotations

from pathlib import Path

import httpx

from skills.skill_loader import load_skill
from skills.skill_manager import get_manager

_INSTALLED_DIR = Path(__file__).parent / "installed"
_TIMEOUT       = httpx.Timeout(15.0)


async def install_from_url(url: str) -> dict:
    """
    Download a skill YAML from `url`, validate it, and install it.

    Returns {"ok": True, "name": skill_name}
         or {"ok": False, "error": "..."}
    """
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get(url)
            r.raise_for_status()
            content = r.text
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"Download failed: {e}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

    _INSTALLED_DIR.mkdir(parents=True, exist_ok=True)

    # Write to a temp name first, then validate
    tmp = _INSTALLED_DIR / "_tmp_skill.yaml"
    try:
        tmp.write_text(content, encoding="utf-8")
        skill = load_skill(tmp)
        if skill is None:
            tmp.unlink(missing_ok=True)
            return {"ok": False, "error": "File is not a valid .skill.yaml"}

        # Move to permanent location
        dest = _INSTALLED_DIR / f"{skill.name}.skill.yaml"
        tmp.rename(dest)
        skill.path = dest

        # Register with the live manager
        get_manager().install(skill)
        return {"ok": True, "name": skill.name, "description": skill.description}

    except Exception as e:
        tmp.unlink(missing_ok=True)
        return {"ok": False, "error": str(e)}


async def uninstall(name: str) -> dict:
    """Remove a user-installed skill by name."""
    ok = get_manager().uninstall(name)
    return {"ok": ok, "name": name}
