"""
skills/skill_manager.py — Mini IDE Milestone B

Manages the full skill registry. Exposes a module-level singleton
so all parts of the backend share one instance.
"""
from __future__ import annotations

from pathlib import Path

from skills.skill_loader import Skill, load_all_from_dir

_BUILTIN_DIR   = Path(__file__).parent / "builtin"
_INSTALLED_DIR = Path(__file__).parent / "installed"


class SkillManager:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}
        self._reload()

    # ── Load ──────────────────────────────────────────────────────────────────
    def _reload(self) -> None:
        self._skills.clear()
        for skill in load_all_from_dir(_BUILTIN_DIR):
            self._skills[skill.name] = skill
        for skill in load_all_from_dir(_INSTALLED_DIR):
            self._skills[skill.name] = skill

    # ── Query ─────────────────────────────────────────────────────────────────
    def list_skills(self) -> list[dict]:
        return [s.to_dict() for s in self._skills.values()]

    def get_active(
        self, file_path: str, imports: list[str] | None = None
    ) -> list[Skill]:
        """Return every enabled skill that matches the current file context."""
        return [
            s for s in self._skills.values()
            if s.enabled and s.matches(file_path, imports)
        ]

    def build_system_prompt_prefix(
        self, file_path: str, imports: list[str] | None = None
    ) -> str:
        """
        Return a skill-derived prefix to prepend to the LLM system prompt.
        Multiple active skills are separated by a blank line.
        """
        active = self.get_active(file_path, imports)
        parts  = [s.system_prompt.strip() for s in active if s.system_prompt.strip()]
        return "\n\n".join(parts)

    def active_names(
        self, file_path: str, imports: list[str] | None = None
    ) -> list[str]:
        return [s.name for s in self.get_active(file_path, imports)]

    # ── Mutation ──────────────────────────────────────────────────────────────
    def enable(self, name: str) -> bool:
        if name in self._skills:
            self._skills[name].enabled = True
            return True
        return False

    def disable(self, name: str) -> bool:
        if name in self._skills:
            self._skills[name].enabled = False
            return True
        return False

    def install(self, skill: Skill) -> None:
        """Register a freshly downloaded skill."""
        self._skills[skill.name] = skill

    def uninstall(self, name: str) -> bool:
        """Remove a user-installed skill (built-ins cannot be removed)."""
        skill = self._skills.get(name)
        if not skill:
            return False
        if skill.path and skill.path.parent == _BUILTIN_DIR:
            return False          # built-ins are read-only
        del self._skills[name]
        if skill.path and skill.path.exists():
            skill.path.unlink(missing_ok=True)
        return True


# ── Module-level singleton ────────────────────────────────────────────────────
_manager: SkillManager | None = None


def get_manager() -> SkillManager:
    global _manager
    if _manager is None:
        _manager = SkillManager()
    return _manager
