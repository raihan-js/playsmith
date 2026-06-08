"""Skill marketplace — discover and install community skills, **safely**.

This is the compounding moat (WHY.md) — and its security is non-negotiable. The threat model:
a community skill's bundled ``scripts/`` become code/automation written into the user's game (and
may run when they play it or build it), and its ``SKILL.md`` body is injected into the agent's
prompt (a prompt-injection vector). So installs must:

  1. **Verify integrity** — the fetched skillpack's SHA-256 must match the curated index entry.
  2. **Refuse untrusted by default** — third-party/untrusted skills require an explicit opt-in.
  3. **Never auto-execute** — installing only writes files; no post-install hooks, ever.
  4. **Record provenance** — source/author/checksum/trusted are written next to the skill so the
     loader can flag it and the studio can warn before its code reaches a game.

A skill is distributed as a single JSON "skillpack": ``{name, version, skill_md, scripts{}}``.
The index lists entries with a ``url`` to the skillpack and its ``sha256``.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import httpx

from playsmith.engines.base import KNOWN_ASSERTIONS
from playsmith.skills.loader import Skill, SkillLoader, parse_frontmatter


class SkillRegistryError(Exception):
    """A marketplace failure (not found, integrity/validation failure, untrusted, etc.)."""


@dataclass
class IndexEntry:
    name: str
    description: str
    url: str
    sha256: str = ""
    version: str = "0.0.0"
    author: str = "unknown"
    trusted: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> IndexEntry:
        return cls(
            name=data["name"],
            description=" ".join((data.get("description") or "").split()),
            url=data.get("url", ""),
            sha256=data.get("sha256", ""),
            version=str(data.get("version", "0.0.0")),
            author=data.get("author", "unknown"),
            trusted=bool(data.get("trusted", True)),
        )


def validate_skillpack(pack: dict) -> list[str]:
    """Return a list of validation errors ([] == valid) against docs/SKILL_SPEC.md."""
    errors: list[str] = []
    name = pack.get("name")
    if not name:
        errors.append("missing 'name'")
    skill_md = pack.get("skill_md")
    if not skill_md:
        errors.append("missing 'skill_md'")
        return errors
    meta, _ = parse_frontmatter(skill_md)
    if not meta.get("name"):
        errors.append("SKILL.md frontmatter missing 'name'")
    elif name and meta.get("name") != name:
        errors.append("pack name != SKILL.md name")
    if not meta.get("description"):
        errors.append("SKILL.md frontmatter missing 'description'")
    unknown = [a for a in (meta.get("assertions") or []) if a not in KNOWN_ASSERTIONS]
    if unknown:
        errors.append(f"unknown assertions {unknown} (see docs/SKILL_SPEC.md)")
    scripts = pack.get("scripts") or {}
    if not isinstance(scripts, dict):
        errors.append("'scripts' must be a map of filename -> content")
    return errors


class SkillRegistry:
    """Fetches the curated index and installs skills into the user skills dir, securely."""

    def __init__(
        self, index_source: str, install_dir: Path, *, client: httpx.Client | None = None
    ) -> None:
        self.index_source = index_source
        self.install_dir = Path(install_dir).expanduser()
        self._client = client

    # -- fetching (local path or http(s)) --------------------------------------
    def _fetch_text(self, source: str) -> str:
        local = Path(source).expanduser()
        if local.exists():
            return local.read_text()
        try:
            resp = (
                self._client.get(source)
                if self._client is not None
                else httpx.get(source, timeout=30)
            )
        except httpx.HTTPError as exc:
            raise SkillRegistryError(f"Could not fetch {source}: {exc}") from exc
        if resp.status_code >= 400:
            raise SkillRegistryError(f"Fetching {source} returned HTTP {resp.status_code}.")
        return resp.text

    def fetch_index(self) -> list[IndexEntry]:
        try:
            data = json.loads(self._fetch_text(self.index_source))
        except json.JSONDecodeError as exc:
            raise SkillRegistryError(f"Registry index is not valid JSON: {exc}") from exc
        return [IndexEntry.from_dict(e) for e in (data.get("skills") or [])]

    def search(self, query: str) -> list[IndexEntry]:
        q = query.lower().strip()
        entries = self.fetch_index()
        if not q:
            return entries
        return [e for e in entries if q in e.name.lower() or q in e.description.lower()]

    def installed(self) -> list[str]:
        if not self.install_dir.is_dir():
            return []
        return sorted(p.name for p in self.install_dir.iterdir() if (p / "SKILL.md").exists())

    # -- install / remove ------------------------------------------------------
    def install(self, name: str, *, allow_untrusted: bool = False) -> Skill:
        entry = next((e for e in self.fetch_index() if e.name == name), None)
        if entry is None:
            raise SkillRegistryError(f"'{name}' is not in the registry index.")
        if not entry.trusted and not allow_untrusted:
            raise SkillRegistryError(
                f"'{name}' is from an UNTRUSTED source ({entry.author}). Its scripts would be "
                "written into your games and its instructions drive the agent. Re-run with "
                "--allow-untrusted only if you trust it."
            )

        raw = self._fetch_text(entry.url)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        if entry.sha256 and digest != entry.sha256:
            raise SkillRegistryError(
                f"Checksum mismatch for '{name}' (index says {entry.sha256[:12]}…, got "
                f"{digest[:12]}…). Refusing to install — the skillpack may be tampered."
            )

        try:
            pack = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SkillRegistryError(f"Skillpack for '{name}' is not valid JSON: {exc}") from exc
        errors = validate_skillpack(pack)
        if errors:
            raise SkillRegistryError(f"'{name}' failed validation: {'; '.join(errors)}")

        # Write files only — NEVER execute anything from the pack.
        dest = self.install_dir / name
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "SKILL.md").write_text(pack["skill_md"])
        scripts = pack.get("scripts") or {}
        if scripts:
            (dest / "scripts").mkdir(exist_ok=True)
            for filename, content in scripts.items():
                safe = Path(str(filename)).name  # strip any path components (no traversal)
                (dest / "scripts" / safe).write_text(str(content))
        (dest / ".provenance.json").write_text(
            json.dumps(
                {
                    "source": entry.url,
                    "author": entry.author,
                    "version": entry.version,
                    "sha256": digest,
                    "trusted": entry.trusted,
                },
                indent=2,
            )
        )
        skill = SkillLoader([self.install_dir]).get(name)
        if skill is None:  # pragma: no cover - defensive
            raise SkillRegistryError(f"'{name}' installed but could not be loaded.")
        return skill

    def remove(self, name: str) -> bool:
        """Remove an installed skill. Only ever touches the user install dir (never repo skills)."""
        dest = (self.install_dir / name).resolve()
        if self.install_dir.resolve() not in dest.parents or not dest.is_dir():
            return False
        shutil.rmtree(dest)
        return True
