"""The Director — dress a cloned UE template into the requested game (CLAUDE.md §0, Stage 3).

The build-on-template clone is already a playable, lit, animated game. The director's job is to
*dress and tune* it: place gameplay objects (obstacles, jump pads, targets, a goal) from a curated
palette of the template's own shipped prototyping assets, set the lighting mood, and name an
objective — all ADDITIVELY on the template's real level (never rebuilding from an empty scene).

A frontier LLM (TaskType.REASONING → routed to the director model) proposes a *dressing spec*; we
clamp it to safe, reachable ranges and apply it via the proven UE Python path. Any LLM failure
falls back to a safe default dressing, so a build never breaks. The critic (next) scores the
rendered result and loops; this module is the "act" half of that loop.
"""

from __future__ import annotations

import json
import re

from playsmith.engines.unreal import critic
from playsmith.llm import LLMGateway, Message, TaskType

# UE units are centimetres; keep the playfield bounded and reachable from the template PlayerStart.
_BOUND_XY = 3000.0
_BOUND_Z = 700.0
_MAX_PLACEMENTS = 40

# Curated palette: friendly name -> (kind, asset path). These ship inside every clone (the
# LevelPrototyping shared pack), so the LLM can only pick known-good, real assets — never a bad ref.
# "mesh" = a StaticMesh placed on a StaticMeshActor; "bp" = a gameplay Blueprint spawned by class.
PALETTE: dict[str, tuple[str, str]] = {
    "cube": ("mesh", "/Game/LevelPrototyping/Meshes/SM_Cube"),
    "chamfer_cube": ("mesh", "/Game/LevelPrototyping/Meshes/SM_ChamferCube"),
    "ramp": ("mesh", "/Game/LevelPrototyping/Meshes/SM_Ramp"),
    "cylinder": ("mesh", "/Game/LevelPrototyping/Meshes/SM_Cylinder"),
    "quarter_cylinder": ("mesh", "/Game/LevelPrototyping/Meshes/SM_QuarterCylinder"),
    "plane": ("mesh", "/Game/LevelPrototyping/Meshes/SM_Plane"),
    "jump_pad": ("bp", "/Game/LevelPrototyping/Interactable/JumpPad/BP_JumpPad"),
    "target": ("bp", "/Game/LevelPrototyping/Interactable/Target/BP_WobbleTarget"),
    "door": ("bp", "/Game/LevelPrototyping/Interactable/Door/BP_DoorFrame"),
}

_SYSTEM = "You are a 3D level designer. Reply with STRICT JSON only — no prose, no code fences."

# Structured hint fields the studio composer can pass through (all optional, free-text-ish).
_HINT_LABELS = (
    ("theme", "Theme"),
    ("vibe", "Mood / vibe"),
    ("difficulty", "Difficulty"),
    ("size", "Level size"),
)


def _hint_lines(hints: dict | None) -> str:
    """Render the player's structured choices into a prompt block the director must honor."""
    if not hints:
        return ""
    parts = [f"{label}: {hints[key]}" for key, label in _HINT_LABELS if hints.get(key)]
    if not parts:
        return ""
    return "PLAYER'S CHOICES (honor these):\n- " + "\n- ".join(parts) + "\n\n"


def fallback_title(prompt: str) -> str:
    """A readable game title from the raw prompt, for when the LLM gives none (Title Case)."""
    words = re.findall(r"[A-Za-z0-9']+", prompt or "")
    return " ".join(w.capitalize() for w in words[:4]) or "Untitled Game"


def _ask(prompt: str, genre: str, hints: dict | None = None) -> str:
    kinds = ", ".join(sorted(PALETTE))
    return (
        f"You are dressing an existing, already-playable {genre} Unreal level (it has a floor, a "
        "player character, and a PlayerStart at the origin). ADD gameplay objects to turn it into "
        "this game; do not remove what's there.\n\n"
        f"GAME: {prompt}\n\n"
        f"{_hint_lines(hints)}"
        f"Place objects from this palette ONLY (kind must be one of): {kinds}.\n"
        "Return STRICT JSON exactly like:\n"
        "{\n"
        '  "title": "<a catchy 2-4 word game title>",\n'
        '  "theme": "<short theme>",\n'
        '  "objective": "<one sentence: what the player does to win>",\n'
        '  "sun": {"color": [r,g,b], "intensity": <2-10>, "pitch": <-80..-10>},\n'
        '  "fog": <0.0-0.1>,\n'
        '  "placements": [\n'
        '    {"kind":"cube","x":<-2500..2500>,"y":<-2500..2500>,"z":<0..600>,'
        '"sx":<1-6>,"sy":<1-6>,"sz":<1-6>,"role":"obstacle|platform|goal|hazard|prop"}, ...\n'
        "  ]\n"
        "}\n"
        "Colour components are 0..1. Use 16-28 placements grouped into 3-4 DISTINCT ZONES along a "
        "route from the player start (near origin) to a clear goal — e.g. a starting clearing, a "
        "climb (platforms at varied z), a hazard gauntlet, and a goal arena. Cluster cover and "
        "obstacles, scatter collectibles between zones, and use jump_pad/target/door where they "
        "fit. Put exactly one placement with role 'goal', set far from the origin (in the last "
        "zone). Match lighting/fog to the mood."
    )


def _num(value, lo: float, hi: float, default: float) -> float:
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return default


def _place(kind, x, y, z, role, sx=1.0, sy=1.0, sz=1.0) -> dict:
    return {"kind": kind, "x": x, "y": y, "z": z, "sx": sx, "sy": sy, "sz": sz, "role": role}


def default_dressing() -> dict:
    """A safe, playable dressing when no LLM spec is available: a short obstacle course + a goal."""
    return {
        "title": "Prototype Course",
        "theme": "prototype course",
        "objective": "Reach the target at the far end of the course.",
        "sun": {"color": [1.0, 0.95, 0.85], "intensity": 6.0, "pitch": -45.0},
        "fog": 0.02,
        "placements": [
            _place("cube", 600, 0, 50, "platform", sx=2, sy=2),
            _place("ramp", 1100, 200, 0, "platform", sx=2, sy=2, sz=2),
            _place("cube", 1600, -200, 100, "obstacle", sx=2, sy=2, sz=2),
            _place("jump_pad", 2000, 0, 20, "prop"),
            _place("target", 2500, 0, 120, "goal"),
        ],
    }


def _sanitize(spec: dict) -> dict:
    """Clamp everything to safe, reachable ranges; drop unknown asset kinds. Never raises."""
    out = default_dressing()
    if isinstance(spec.get("title"), str) and spec["title"].strip():
        out["title"] = spec["title"].strip()[:48]
    if isinstance(spec.get("theme"), str) and spec["theme"].strip():
        out["theme"] = spec["theme"].strip()[:60]
    if isinstance(spec.get("objective"), str) and spec["objective"].strip():
        out["objective"] = spec["objective"].strip()[:140]
    sun = spec.get("sun") or {}
    color = sun.get("color")
    if isinstance(color, list) and len(color) == 3:
        out["sun"]["color"] = [_num(c, 0.0, 1.0, 1.0) for c in color]
    out["sun"]["intensity"] = _num(sun.get("intensity"), 1.0, 12.0, 6.0)
    out["sun"]["pitch"] = _num(sun.get("pitch"), -85.0, -5.0, -45.0)
    out["fog"] = _num(spec.get("fog"), 0.0, 0.1, 0.02)
    placements = spec.get("placements")
    if isinstance(placements, list):
        clean = []
        for p in placements[:_MAX_PLACEMENTS]:
            if not isinstance(p, dict) or p.get("kind") not in PALETTE:
                continue
            clean.append(
                {
                    "kind": p["kind"],
                    "x": _num(p.get("x"), -_BOUND_XY, _BOUND_XY, 0.0),
                    "y": _num(p.get("y"), -_BOUND_XY, _BOUND_XY, 0.0),
                    "z": _num(p.get("z"), 0.0, _BOUND_Z, 100.0),
                    "sx": _num(p.get("sx"), 0.2, 8.0, 1.0),
                    "sy": _num(p.get("sy"), 0.2, 8.0, 1.0),
                    "sz": _num(p.get("sz"), 0.2, 8.0, 1.0),
                    "role": str(p.get("role", "prop"))[:20],
                }
            )
        if clean:
            out["placements"] = clean
    return out


def plan_dressing(
    prompt: str, genre: str, gateway: LLMGateway, *, hints: dict | None = None
) -> dict:
    """Ask the (frontier) LLM for a themed dressing spec; fall back to a safe default on failure.

    ``hints`` carries the studio composer's structured choices (theme/vibe/difficulty/size) so the
    player can be more directive than a single free-text line. A safe title is always present.
    """
    out = default_dressing()
    out["title"] = fallback_title(prompt)
    try:
        resp = gateway.chat(
            [Message.system(_SYSTEM), Message.user(_ask(prompt, genre, hints))],
            task=TaskType.REASONING,
        )
        match = re.search(r"\{.*\}", resp.content or "", re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                spec = _sanitize(parsed)
                # If the model gave no title, sanitize used the generic default — prefer the prompt.
                if spec["title"] == default_dressing()["title"]:
                    spec["title"] = fallback_title(prompt)
                return spec
    except Exception:  # noqa: BLE001 - direction must never break a build
        pass
    return out


# Kinds/roles the deterministic augmenter cycles through for variety (all known-good palette refs).
_AUGMENT_KINDS = ("cube", "ramp", "cylinder", "chamfer_cube", "quarter_cylinder", "jump_pad")
_AUGMENT_ROLES = ("platform", "obstacle", "cover", "collectible", "hazard")
# A route through 4 distinct areas (cm): a start clearing, a climb, a hazard gauntlet, a goal arena.
_ZONE_CENTERS = ((650.0, 0.0), (1450.0, 650.0), (1800.0, -700.0), (2550.0, 0.0))


def _augment(spec: dict, *, size: str | None = None) -> dict:
    """Deterministically enrich a dressing into distinct, varied, vertical **zones** until it hits
    the size target, guaranteeing exactly one far goal. Makes real progress with no LLM in the loop.

    Spreads additions across :data:`_ZONE_CENTERS` (a designed route) rather than one straight line,
    so the result reads as several areas — the multi-area feel the critic now rewards.
    """
    out = _sanitize(spec)  # normalize + clamp the incoming spec first
    placements = list(out["placements"])
    target_n = critic.target_count(size)
    while len(placements) < min(target_n + 4, _MAX_PLACEMENTS):
        k = len(placements)
        cx, cy = _ZONE_CENTERS[k % len(_ZONE_CENTERS)]  # round-robin through the zones
        ox = float((k * 53) % 420) - 210.0  # deterministic jitter within the zone
        oy = float((k * 97) % 420) - 210.0
        kind = _AUGMENT_KINDS[k % len(_AUGMENT_KINDS)]
        role = _AUGMENT_ROLES[k % len(_AUGMENT_ROLES)]
        x = max(-_BOUND_XY + 150, min(_BOUND_XY - 150, cx + ox))
        y = max(-_BOUND_XY + 150, min(_BOUND_XY - 150, cy + oy))
        z = 50.0 + 100.0 * ((k // len(_ZONE_CENTERS)) % 4)  # layered heights -> verticality
        placements.append(_place(kind, x, y, z, role, sx=1.4, sy=1.4, sz=1.0 + (k % 3)))
    # Exactly one goal, set in the far zone — demote any extras to props.
    seen_goal = False
    for p in placements:
        if p.get("role") == "goal":
            if seen_goal:
                p["role"] = "prop"
            seen_goal = True
    if not seen_goal:
        gx, gy = _ZONE_CENTERS[-1]
        placements.append(_place("target", gx, gy, 120.0, "goal"))
    out["placements"] = placements[:_MAX_PLACEMENTS]
    return out


def _improve_ask(prompt: str, genre: str, spec: dict, crit, hints: dict | None = None) -> str:
    issues = "\n".join(f"- {f}" for f in crit.feedback) or "- Make it richer and more varied."
    current = json.dumps({"placements": spec.get("placements", [])})[:2000]
    return (
        f"You are improving an existing {genre} Unreal level dressing for this game:\n"
        f"GAME: {prompt}\n\n"
        f"{_hint_lines(hints)}"
        f"A critic scored it {crit.score}/100 and wants you to fix:\n{issues}\n\n"
        f"Current placements (JSON): {current}\n\n"
        "Return STRICT JSON in the SAME schema as before (title, theme, objective, sun, fog, "
        "placements). KEEP the good placements and ADD more to address every point above — aim for "
        "a denser, more varied, more vertical level. Use only these kinds: "
        f"{', '.join(sorted(PALETTE))}. Keep exactly one placement with role 'goal', far from "
        "the origin."
    )


def improve_dressing(
    prompt: str, genre: str, gateway: LLMGateway, spec: dict, crit, *, hints: dict | None = None
) -> dict:
    """Given the critic's verdict, produce a richer dressing for the next iteration.

    Tries the frontier model for a creative upgrade; on any failure — or a reply that isn't
    genuinely richer than what we have — falls back to a deterministic augmentation, so every
    director→critic iteration measurably improves the level (the loop never stalls). The title is
    preserved across iterations.
    """
    size = (hints or {}).get("size")
    base_n = len(spec.get("placements") or [])
    try:
        resp = gateway.chat(
            [Message.system(_SYSTEM), Message.user(_improve_ask(prompt, genre, spec, crit, hints))],
            task=TaskType.REASONING,
        )
        match = re.search(r"\{.*\}", resp.content or "", re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                improved = _sanitize(parsed)
                improved["title"] = spec.get("title") or improved["title"]
                if len(improved["placements"]) > base_n:  # accept only a genuinely richer plan
                    return improved
    except Exception:  # noqa: BLE001 - improvement must never break a build
        pass
    return _augment(spec, size=size)


def dress_level_script(spec: dict, map_path: str) -> str:
    """UE Python that loads the template level and ADDS the dressing, then writes PLAYSMITH_ASSERT.

    Additive on the real template level (loads, never new_level). Static meshes go on actors;
    palette Blueprints (jump pad, target, door) are spawned by class. Each gets its role as a tag so
    later steps (and the critic) can reason about it. Results come back via ``$PLAYSMITH_UE_OUT``.
    """
    spec_json = json.dumps(spec)
    palette_json = json.dumps(PALETTE)
    return (
        "import json, os\n"
        "import unreal\n"
        f'MAP = "{map_path}"\n'
        f"SPEC = json.loads(r'''{spec_json}''')\n"
        f"PALETTE = json.loads(r'''{palette_json}''')\n"
        'OUT = os.environ.get("PLAYSMITH_UE_OUT", "")\n'
        "les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)\n"
        "eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)\n"
        "loaded = les.load_level(MAP)\n"
        # Idempotent re-dressing: remove objects a previous Playsmith pass placed (labelled PS_*)
        # so the director→critic loop REPLACES its dressing each iteration instead of stacking it.
        "for _a in list(eas.get_all_level_actors()):\n"
        "    try:\n"
        "        if _a.get_actor_label().startswith('PS_'):\n"
        "            eas.destroy_actor(_a)\n"
        "    except Exception:\n"
        "        pass\n"
        "placed = 0\n"
        "def _spawn_mesh(path, x, y, z, sx, sy, sz, tag, label):\n"
        "    mesh = unreal.EditorAssetLibrary.load_asset(path)\n"
        "    if mesh is None:\n"
        "        return False\n"
        "    a = eas.spawn_actor_from_class("
        "unreal.StaticMeshActor, unreal.Vector(x, y, z), unreal.Rotator(0, 0, 0))\n"
        "    a.static_mesh_component.set_static_mesh(mesh)\n"
        "    a.set_actor_scale3d(unreal.Vector(sx, sy, sz))\n"
        "    a.set_actor_label(label)\n"
        "    a.set_mobility(unreal.ComponentMobility.MOVABLE)\n"
        "    a.tags = [unreal.Name(tag)]\n"
        "    return True\n"
        "def _spawn_bp(path, x, y, z, tag, label):\n"
        "    cls = unreal.EditorAssetLibrary.load_blueprint_class(path)\n"
        "    if cls is None:\n"
        "        return False\n"
        "    a = eas.spawn_actor_from_class(cls, unreal.Vector(x, y, z), unreal.Rotator(0, 0, 0))\n"
        "    a.set_actor_label(label)\n"
        "    a.tags = [unreal.Name(tag)]\n"
        "    return True\n"
        "for i, p in enumerate(SPEC.get('placements', [])):\n"
        "    entry = PALETTE.get(p.get('kind'))\n"
        "    if not entry:\n"
        "        continue\n"
        "    kind_type, path = entry[0], entry[1]\n"
        "    role = p.get('role', 'prop')\n"
        "    label = 'PS_%s_%d' % (p.get('kind'), i)\n"
        "    try:\n"
        "        if kind_type == 'mesh':\n"
        "            ok = _spawn_mesh(path, p['x'], p['y'], p['z'], "
        "p.get('sx', 1), p.get('sy', 1), p.get('sz', 1), role, label)\n"
        "        else:\n"
        "            ok = _spawn_bp(path, p['x'], p['y'], p['z'], role, label)\n"
        "        if ok:\n"
        "            placed += 1\n"
        "    except Exception as e:\n"
        "        unreal.log_warning('PLAYSMITH placement skipped: %s' % e)\n"
        "# Lighting mood: tune the template's DirectionalLight if present.\n"
        "try:\n"
        "    sun = next((a for a in eas.get_all_level_actors() "
        "if isinstance(a, unreal.DirectionalLight)), None)\n"
        "    sc = SPEC.get('sun', {})\n"
        "    if sun is not None:\n"
        "        sun.light_component.set_intensity(float(sc.get('intensity', 6.0)))\n"
        "        col = sc.get('color', [1.0, 0.95, 0.85])\n"
        "        sun.light_component.set_light_color("
        "unreal.Color(int(col[0]*255), int(col[1]*255), int(col[2]*255)))\n"
        "        sun.set_actor_rotation("
        "unreal.Rotator(float(sc.get('pitch', -45.0)), 0, 0), False)\n"
        "except Exception as e:\n"
        "    unreal.log_warning('PLAYSMITH lighting skipped: %s' % e)\n"
        # World Partition stores actors as external packages — save_current_level alone drops the
        # new actors; save_dirty_packages flushes the spawned external-actor packages to disk.
        "unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)\n"
        "unreal.log('PLAYSMITH placed %d objects' % placed)\n"
        "has_goal = any(p.get('role') == 'goal' for p in SPEC.get('placements', []))\n"
        "lines = [\n"
        "    'PLAYSMITH_ASSERT level_loads=%s' % ('true' if loaded else 'false'),\n"
        "    'PLAYSMITH_ASSERT objects_placed=%s' % ('true' if placed > 0 else 'false'),\n"
        "    'PLAYSMITH_ASSERT goal_exists=%s' % ('true' if has_goal else 'false'),\n"
        "]\n"
        "if OUT:\n"
        "    with open(OUT, 'w') as f:\n"
        "        f.write('\\n'.join(lines) + '\\n')\n"
    )
