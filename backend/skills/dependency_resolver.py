"""
skills/dependency_resolver.py — Mini IDE Milestone B

Simple topological sort for skill dependencies.
E.g. fastapi-expert depends on python-expert →
     python-expert's system prompt is prepended first.
"""
from __future__ import annotations


def resolve_order(skills: list, all_skills: dict) -> list:
    """
    Return skills in dependency order (dependencies first).

    Args:
        skills:     list of Skill objects to order
        all_skills: dict[name → Skill] of all registered skills

    If a dependency is missing or a cycle is detected the skill is
    included anyway rather than blocking the user.
    """
    ordered: list  = []
    visited:  set  = set()

    def visit(skill) -> None:
        if skill.name in visited:
            return
        visited.add(skill.name)
        for dep_name in skill.dependencies:
            dep = all_skills.get(dep_name)
            if dep and dep.enabled:
                visit(dep)
        ordered.append(skill)

    for s in skills:
        visit(s)

    return ordered
