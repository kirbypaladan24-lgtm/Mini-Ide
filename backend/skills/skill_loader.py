"""
skills/skill_loader.py — Mini IDE Milestone B

Parses .skill.yaml files into Skill dataclass instances.
Falls back gracefully if PyYAML is not installed.
"""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import yaml
    YAML_OK = True
except ImportError:
    yaml    = None      # type: ignore
    YAML_OK = False


@dataclass
class Skill:
    name:          str
    version:       str
    description:   str
    triggers:      dict                  # {imports:[...], file_patterns:[...]}
    system_prompt: str
    docs:          list[dict]
    dependencies:  list[str]
    path:          Optional[Path] = None
    enabled:       bool           = True

    # ── Matching ──────────────────────────────────────────────────────────────
    def matches(self, file_path: str, imports: list[str] | None = None) -> bool:
        """
        Return True if this skill should activate for the given file.

        Logic:
          • file_patterns must match (if any are specified)
          • trigger imports must overlap with detected imports (if any specified)
          • if no triggers at all → always match
        """
        patterns = self.triggers.get("file_patterns", [])
        if patterns:
            if not any(fnmatch.fnmatch(file_path, p) for p in patterns):
                return False

        trigger_imports = self.triggers.get("imports", [])
        if trigger_imports:
            detected = set(imports or [])
            if not any(t in detected for t in trigger_imports):
                return False

        return True

    def to_dict(self) -> dict:
        return {
            "name":        self.name,
            "version":     self.version,
            "description": self.description,
            "enabled":     self.enabled,
            "triggers":    self.triggers,
            "path":        str(self.path) if self.path else None,
        }


# ── Loader ────────────────────────────────────────────────────────────────────
def load_skill(path: Path) -> Optional[Skill]:
    """
    Parse a .skill.yaml file and return a Skill, or None on any error.
    """
    if not YAML_OK:
        return None
    try:
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text) or {}
        return Skill(
            name          = str(data.get("name", path.stem)),
            version       = str(data.get("version", "1.0.0")),
            description   = str(data.get("description", "")),
            triggers      = dict(data.get("triggers", {})),
            system_prompt = str(data.get("system_prompt", "")),
            docs          = list(data.get("docs", [])),
            dependencies  = list(data.get("dependencies", [])),
            path          = path,
        )
    except Exception:
        return None


def load_all_from_dir(directory: Path) -> list[Skill]:
    """Load all .skill.yaml files from a directory."""
    if not directory.exists():
        return []
    skills = []
    for p in sorted(directory.glob("*.skill.yaml")):
        s = load_skill(p)
        if s:
            skills.append(s)
    return skills
