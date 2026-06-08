"""Skills engine — SKILL.md loader with progressive disclosure + prompt routing."""

from playsmith.skills.loader import (
    DEFAULT_SKILLS_ROOT,
    USER_SKILLS_DIR,
    Skill,
    SkillError,
    SkillLoader,
    parse_frontmatter,
)
from playsmith.skills.registry import (
    IndexEntry,
    SkillRegistry,
    SkillRegistryError,
    validate_skillpack,
)
from playsmith.skills.router import SkillRouter

__all__ = [
    "DEFAULT_SKILLS_ROOT",
    "USER_SKILLS_DIR",
    "IndexEntry",
    "Skill",
    "SkillError",
    "SkillLoader",
    "SkillRegistry",
    "SkillRegistryError",
    "SkillRouter",
    "parse_frontmatter",
    "validate_skillpack",
]
