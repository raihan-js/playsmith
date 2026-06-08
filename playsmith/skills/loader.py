"""SKILL.md loader with progressive disclosure.

A skill is a folder with a ``SKILL.md`` (YAML frontmatter: name + description, then a
markdown body) plus optional ``scripts/`` and ``references/`` (docs/ARCHITECTURE.md §5).

Progressive disclosure, three levels:
  1. metadata (name + description) — parsed at scan time, tiny, used for routing;
  2. body — loaded only when a skill is selected;
  3. bundled resources — paths exposed, contents read only when a step needs them.

We use the open SKILL.md standard (no bespoke format) so skills interoperate with other
agent tooling (CLAUDE.md §8).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from playsmith.config import REPO_ROOT

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)

# Where skills are discovered. Local dir at MVP; a community registry comes in Phase 2.
DEFAULT_SKILLS_ROOT = REPO_ROOT / "game-skills"


class SkillError(Exception):
    """Raised when a skill is malformed or missing."""


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split a SKILL.md into (frontmatter dict, body markdown)."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    meta = yaml.safe_load(match.group(1)) or {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, match.group(2)


@dataclass
class Skill:
    """A game-generation skill. Metadata is eager; body/resources load lazily."""

    name: str
    description: str
    path: Path  # the SKILL.md file
    _body: str | None = field(default=None, repr=False)

    @property
    def dir(self) -> Path:
        return self.path.parent

    def body(self) -> str:
        """Load and cache the markdown body (level 2 of progressive disclosure)."""
        if self._body is None:
            _, body = parse_frontmatter(self.path.read_text())
            self._body = body.strip()
        return self._body

    def scripts(self) -> dict[str, Path]:
        """Map bundled script filenames to paths — paths only, not contents (level 3)."""
        scripts_dir = self.dir / "scripts"
        if not scripts_dir.is_dir():
            return {}
        return {p.name: p for p in sorted(scripts_dir.iterdir()) if p.is_file()}

    def references(self) -> dict[str, Path]:
        refs_dir = self.dir / "references"
        if not refs_dir.is_dir():
            return {}
        return {p.name: p for p in sorted(refs_dir.iterdir()) if p.is_file()}

    def read_script(self, name: str) -> str:
        """Read one bundled script on demand."""
        scripts = self.scripts()
        if name not in scripts:
            raise SkillError(f"Skill '{self.name}' has no bundled script '{name}'.")
        return scripts[name].read_text()


class SkillLoader:
    """Discovers skills under one or more roots."""

    def __init__(self, roots: list[Path] | None = None) -> None:
        self.roots = roots or [DEFAULT_SKILLS_ROOT]

    def discover(self) -> list[Skill]:
        """Scan roots for ``SKILL.md`` files and parse their metadata."""
        skills: list[Skill] = []
        seen: set[str] = set()
        for root in self.roots:
            if not root.exists():
                continue
            for skill_md in sorted(root.rglob("SKILL.md")):
                skill = self._load_metadata(skill_md)
                if skill is None or skill.name in seen:
                    continue
                seen.add(skill.name)
                skills.append(skill)
        return skills

    @staticmethod
    def _load_metadata(skill_md: Path) -> Skill | None:
        try:
            meta, _ = parse_frontmatter(skill_md.read_text())
        except (OSError, yaml.YAMLError):
            return None
        name = (meta.get("name") or "").strip()
        description = " ".join((meta.get("description") or "").split())
        if not name:
            return None
        return Skill(name=name, description=description, path=skill_md)

    def get(self, name: str) -> Skill | None:
        for skill in self.discover():
            if skill.name == name:
                return skill
        return None
