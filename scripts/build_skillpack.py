#!/usr/bin/env python3
"""Build marketplace skillpacks + an index.json from skill folders.

A skillpack is a single JSON bundling a skill's SKILL.md + scripts (see
docs/SKILL_SPEC.md and playsmith/skills/registry.py). This tool turns one or more skill
folders into ``<name>.skillpack.json`` files plus an ``index.json`` with SHA-256 checksums,
ready to publish to a curated registry repo.

Usage:
    python scripts/build_skillpack.py --out <dir> --base-url <raw-url-base> \
        --author <name> <skill_dir> [<skill_dir> ...]
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from playsmith.skills import parse_frontmatter


def build_skillpack(skill_dir: Path) -> dict:
    md = (skill_dir / "SKILL.md").read_text()
    meta, _ = parse_frontmatter(md)
    scripts: dict[str, str] = {}
    scripts_dir = skill_dir / "scripts"
    if scripts_dir.is_dir():
        for path in sorted(scripts_dir.iterdir()):
            if path.is_file():
                scripts[path.name] = path.read_text()
    return {
        "name": meta["name"],
        "version": str(meta.get("version", "1.0.0")),
        "skill_md": md,
        "scripts": scripts,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("skill_dirs", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, required=True, help="Output directory for the registry.")
    ap.add_argument("--base-url", required=True, help="Raw URL base where files will be served.")
    ap.add_argument("--author", default="playsmith", help="Author recorded in the index.")
    ap.add_argument("--trusted", action="store_true", help="Mark entries as trusted (curated).")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    base = args.base_url.rstrip("/")
    entries = []
    for skill_dir in args.skill_dirs:
        pack = build_skillpack(skill_dir)
        raw = json.dumps(pack)  # the EXACT bytes we hash and write (registry re-hashes them)
        filename = f"{pack['name']}.skillpack.json"
        (args.out / filename).write_text(raw)
        meta, _ = parse_frontmatter(pack["skill_md"])
        entries.append(
            {
                "name": pack["name"],
                "description": " ".join((meta.get("description") or "").split()),
                "url": f"{base}/{filename}",
                "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                "version": pack["version"],
                "author": args.author,
                "trusted": bool(args.trusted),
            }
        )
        print(f"built {filename} ({entries[-1]['sha256'][:12]}…)")

    (args.out / "index.json").write_text(json.dumps({"skills": entries}, indent=2))
    print(f"wrote {args.out / 'index.json'} with {len(entries)} skill(s)")


if __name__ == "__main__":
    main()
