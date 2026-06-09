"""Real-asset dressing — Fab / Quixel Megascans asset packs (NEXTGEN_ROADMAP Phase 1).

The single biggest visible leap from "prototype" to "real game" is dressing with **real assets**
(photo-scanned Megascans rocks/ruins/foliage, Fab modular kits) instead of grey prototype cubes —
and that's an *orchestration* problem, which is what Playsmith is.

This module is the asset layer:
  * :class:`AssetPack` — a themed set of real meshes the director places, keyed by gameplay role.
  * :data:`BUILTIN_PACK` — the always-available fallback (the LevelPrototyping shapes that ship in
    every clone), so dressing works even with **no** Megascans content installed.
  * :func:`discover_script` — UE Python that runs in the **live editor** (over Remote Control) and
    *categorises whatever real assets are actually installed* under the Megascans/Fab content roots
    — never a hard-coded path, so never a bad ref.
  * :func:`load_manifest_packs` — community-/user-authored pack manifests (JSON), like skills.
  * :func:`resolve_pack` — pick the best pack for a theme (discovered > manifest > builtin).

The director then dresses with the resolved pack: real meshes keep their photoreal materials (no
tint), the ground gets a Megascans surface, and only the builtin prototype fallback is role-tinted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# Gameplay roles the director places (must match director._ROLE_* / placement "role" values).
ROLES = ("platform", "obstacle", "cover", "hazard", "collectible", "goal", "prop")

# Content roots where Fab / Quixel Bridge / Megascans drop imported assets (varies by version/setup;
# we discover whatever exists under any of these — missing roots are simply skipped).
MEGASCANS_ROOTS: tuple[str, ...] = (
    "/Game/Megascans",
    "/Game/MSPresets",
    "/Game/Megascans_Trees",
    "/Game/Fab",
    "/Game/Quixel",
    "/Game/Surfaces",
    "/Game/Assets",
)

# Keyword → role, longest/most-specific first. Used to bucket discovered assets by their name.
_CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("goal", ("shrine", "throne", "portal", "gate", "monument", "beacon", "totem", "obelisk",
              "altar", "statue")),
    ("collectible", ("gem", "crystal", "shard", "coin", "relic", "orb", "treasure", "chest",
                     "gold", "jewel", "loot")),
    ("hazard", ("spike", "thorn", "trap", "lava", "fire", "ember", "hazard", "sharp", "spire")),
    ("platform", ("floor", "platform", "slab", "ground", "path", "road", "tile", "deck", "stair",
                  "step", "bridge")),
    ("cover", ("crate", "barrel", "container", "debris", "rubble", "wreck", "tree", "plant", "bush",
               "fern", "foliage", "vine", "log", "shrub", "trunk")),
    ("obstacle", ("wall", "rock", "cliff", "boulder", "pillar", "column", "ruin", "build", "arch",
                  "block", "stone", "wreckage", "rubblepile", "mountain")),
)
_GROUND_KEYWORDS = ("ground", "snow", "sand", "rock", "floor", "dirt", "grass", "gravel", "ice",
                    "stone", "moss", "mud", "terrain", "surface")


def default_packs_dir() -> Path:
    """Where user-/community-authored asset-pack manifests live (``~/.playsmith/assetpacks``)."""
    return Path("~/.playsmith/assetpacks").expanduser()


def categorize(asset_name: str) -> str:
    """Bucket a discovered asset into a gameplay role from its name (defaults to ``prop``)."""
    n = (asset_name or "").lower()
    for role, keys in _CATEGORY_KEYWORDS:
        if any(k in n for k in keys):
            return role
    return "prop"


@dataclass(frozen=True)
class AssetPack:
    """A themed set of real assets the director dresses with, keyed by gameplay role."""

    name: str
    theme: str
    source: str  # "megascans" | "fab" | "manifest" | "builtin"
    by_role: dict[str, list[str]] = field(default_factory=dict)  # role -> content paths
    ground_material: str | None = None  # a surface material for the floor

    @property
    def is_real(self) -> bool:
        """Real assets keep their own materials; only the builtin fallback is role-tinted."""
        return self.source != "builtin"

    def assets_for(self, role: str) -> list[str]:
        """Meshes for a role — the role's bucket, else props, else any non-empty bucket."""
        if self.by_role.get(role):
            return self.by_role[role]
        if self.by_role.get("prop"):
            return self.by_role["prop"]
        for paths in self.by_role.values():
            if paths:
                return paths
        return []

    def to_dict(self) -> dict:
        return {
            "name": self.name, "theme": self.theme, "source": self.source,
            "by_role": self.by_role, "ground_material": self.ground_material,
        }


# The always-available fallback: the LevelPrototyping shapes every clone ships, mapped to roles.
# (Defined here, not imported from director, to keep this module dependency-free.)
_PROTO = "/Game/LevelPrototyping/Meshes/"
BUILTIN_PACK = AssetPack(
    name="Prototype shapes",
    theme="",
    source="builtin",
    by_role={
        "platform": [_PROTO + "SM_Cube", _PROTO + "SM_Ramp"],
        "obstacle": [_PROTO + "SM_Cube", _PROTO + "SM_ChamferCube"],
        "cover": [_PROTO + "SM_Cube", _PROTO + "SM_ChamferCube"],
        "hazard": [_PROTO + "SM_Cylinder", _PROTO + "SM_QuarterCylinder"],
        "collectible": [_PROTO + "SM_Cylinder"],
        "goal": [_PROTO + "SM_Cube"],
        "prop": [_PROTO + "SM_Cube", _PROTO + "SM_ChamferCube", _PROTO + "SM_Cylinder"],
    },
)


def pack_from_discovery(theme: str, discovered: dict) -> AssetPack:
    """Build a pack from the JSON a live-editor discovery wrote (``{by_role, ground_material}``)."""
    by_role = {
        role: [p for p in (discovered.get("by_role", {}).get(role) or []) if isinstance(p, str)]
        for role in ROLES
    }
    return AssetPack(
        name=discovered.get("name") or "Discovered assets",
        theme=theme,
        source=discovered.get("source") or "megascans",
        by_role={r: paths for r, paths in by_role.items() if paths},
        ground_material=discovered.get("ground_material"),
    )


def load_manifest_packs(packs_dir: str | Path) -> list[AssetPack]:
    """Load user-/community-authored asset-pack manifests (``*.json``) from a directory.

    A manifest is ``{name, theme, source?, by_role: {role: [paths]}, ground_material?}``. Malformed
    files are skipped. This is how someone shares a curated Megascans/Fab pack for a theme.
    """
    out: list[AssetPack] = []
    base = Path(packs_dir).expanduser()
    if not base.is_dir():
        return out
    for path in sorted(base.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict) or not isinstance(data.get("by_role"), dict):
            continue
        by_role = {
            r: [p for p in v if isinstance(p, str)]
            for r, v in data["by_role"].items()
            if r in ROLES and isinstance(v, list)
        }
        out.append(
            AssetPack(
                name=str(data.get("name") or path.stem),
                theme=str(data.get("theme") or ""),
                source=str(data.get("source") or "manifest"),
                by_role={r: p for r, p in by_role.items() if p},
                ground_material=data.get("ground_material"),
            )
        )
    return out


def _matches_theme(pack: AssetPack, theme: str) -> bool:
    t, pt = (theme or "").lower(), (pack.theme or "").lower()
    return bool(pt) and (pt in t or t in pt or any(w in t for w in pt.split()))


def resolve_pack(
    theme: str,
    *,
    discovered: dict | None = None,
    manifests: list[AssetPack] | None = None,
) -> AssetPack:
    """Pick the best pack for a theme: live discovery > a matching manifest > builtin fallback.

    Always returns a usable pack — :data:`BUILTIN_PACK` when nothing real is available — so dressing
    never fails for lack of assets; it just gets *better* the moment Megascans/Fab content exists.
    """
    if discovered and any(discovered.get("by_role", {}).values()):
        return pack_from_discovery(theme, discovered)
    for pack in manifests or []:
        if _matches_theme(pack, theme) and any(pack.by_role.values()):
            return pack
    for pack in manifests or []:  # a themeless/generic manifest pack still beats prototype cubes
        if not pack.theme and any(pack.by_role.values()):
            return pack
    return BUILTIN_PACK


def discover_script(out_json: str, roots: tuple[str, ...] = MEGASCANS_ROOTS) -> str:
    """UE Python (run in the LIVE editor) that categorises installed real assets into a pack JSON.

    Lists StaticMeshes under each existing content root, buckets them by role from their name, and
    finds a ground surface material — then writes ``out_json``. Designed for Remote Control
    execution (the editor has the registry loaded); never raises.
    """
    roots_json = json.dumps(list(roots))
    cat_json = json.dumps([[role, list(keys)] for role, keys in _CATEGORY_KEYWORDS])
    ground_json = json.dumps(list(_GROUND_KEYWORDS))
    return (
        "import json, os\n"
        "import unreal\n"
        f"ROOTS = json.loads(r'''{roots_json}''')\n"
        f"CATS = json.loads(r'''{cat_json}''')\n"
        f"GROUND = json.loads(r'''{ground_json}''')\n"
        f"OUT = r'{out_json}'\n"
        "def _role(name):\n"
        "    n = name.lower()\n"
        "    for role, keys in CATS:\n"
        "        if any(k in n for k in keys):\n"
        "            return role\n"
        "    return 'prop'\n"
        "by_role = {}\n"
        "ground = None\n"
        "count = 0\n"
        "try:\n"
        "    ar = unreal.AssetRegistryHelpers.get_asset_registry()\n"
        "    for root in ROOTS:\n"
        "        if not unreal.EditorAssetLibrary.does_directory_exist(root):\n"
        "            continue\n"
        "        for ap in unreal.EditorAssetLibrary.list_assets(root, recursive=True):\n"
        "            path = ap.split('.')[0]\n"
        "            name = path.split('/')[-1]\n"
        "            cls = ''\n"
        "            try:\n"
        "                data = ar.get_asset_by_object_path(ap)\n"
        "                cls = str(data.asset_class_path.asset_name) if data else ''\n"
        "            except Exception:\n"
        "                cls = ''\n"
        "            _ln = name.lower()\n"
        "            _mesh = cls == 'StaticMesh' or '/meshes/' in path.lower()\n"
        "            if _mesh or _ln.startswith('sm_'):\n"
        "                by_role.setdefault(_role(name), [])\n"
        "                if len(by_role[_role(name)]) < 12:\n"
        "                    by_role[_role(name)].append(path)\n"
        "                count += 1\n"
        "            elif ground is None and cls in ('Material', 'MaterialInstanceConstant'):\n"
        "                if any(g in name.lower() for g in GROUND):\n"
        "                    ground = path\n"
        "except Exception as e:\n"
        "    unreal.log_warning('PLAYSMITH asset discovery failed: %s' % e)\n"
        "result = {'source': 'megascans', 'name': 'Discovered assets', "
        "'by_role': by_role, 'ground_material': ground, 'count': count}\n"
        "try:\n"
        "    with open(OUT, 'w') as f:\n"
        "        json.dump(result, f)\n"
        "except Exception as e:\n"
        "    unreal.log_warning('PLAYSMITH discovery write failed: %s' % e)\n"
    )
