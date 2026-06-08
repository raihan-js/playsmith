"""Skills engine — SKILL.md loader with progressive disclosure + prompt routing."""

from playsmith.skills.loader import (
    DEFAULT_SKILLS_ROOT,
    Skill,
    SkillError,
    SkillLoader,
    parse_frontmatter,
)
from playsmith.skills.router import SkillRouter

__all__ = [
    "DEFAULT_SKILLS_ROOT",
    "Skill",
    "SkillError",
    "SkillLoader",
    "SkillRouter",
    "parse_frontmatter",
]
