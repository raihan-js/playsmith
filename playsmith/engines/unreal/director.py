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

from playsmith.engines.unreal import assetpacks, critic
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
        '  "character": {"prefer": "<empty, or a character name to use if it ships>", '
        '"tint": [r,g,b]},\n'
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
        "zone). Use generous scales (sx/sy around 2-5) so objects read at a distance and fill the "
        "space — not tiny specks on a huge floor. Match lighting/fog to the mood, and give the "
        "character a tint that fits the theme (fiery red for lava, pale blue ice, green jungle)."
    )


def _num(value, lo: float, hi: float, default: float) -> float:
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return default


def _place(kind, x, y, z, role, sx=1.0, sy=1.0, sz=1.0) -> dict:
    return {"kind": kind, "x": x, "y": y, "z": z, "sx": sx, "sy": sy, "sz": sz, "role": role}


# Deterministic theme palettes keyed off prompt keywords, so a "frozen" prompt always yields an
# ICY level (blue/white structure, cool light, pale character) regardless of how good — or absent —
# the LLM's plan is. ``structure`` colours the bulk objects; gameplay roles (hazard/collectible/
# goal) keep fixed, readable accents so the level stays legible against any theme.
_THEMES: tuple[dict, ...] = (
    {"name": "frozen fortress", "structure": [0.62, 0.78, 0.92], "sun": [0.72, 0.84, 1.0],
     "intensity": 5.0, "pitch": -32.0, "fog": 0.05, "character": [0.55, 0.78, 0.95],
     "keys": ("frozen", "ice", "icy", "snow", "glacier", "arctic", "winter", "tundra", "frost",
              "blizzard", "cryo")},
    {"name": "volcanic", "structure": [0.30, 0.17, 0.15], "sun": [1.0, 0.5, 0.28],
     "intensity": 6.0, "pitch": -28.0, "fog": 0.045, "character": [0.85, 0.28, 0.12],
     "keys": ("lava", "volcan", "magma", "fire", "ember", "inferno", "molten", "fiery", "scorch")},
    {"name": "overgrown jungle", "structure": [0.30, 0.44, 0.24], "sun": [0.85, 0.95, 0.7],
     "intensity": 5.5, "pitch": -42.0, "fog": 0.04, "character": [0.35, 0.55, 0.30],
     "keys": ("jungle", "forest", "wood", "swamp", "overgrow", "vine", "foliage", "rainforest")},
    {"name": "desert ruins", "structure": [0.82, 0.68, 0.42], "sun": [1.0, 0.92, 0.7],
     "intensity": 7.0, "pitch": -52.0, "fog": 0.02, "character": [0.80, 0.65, 0.40],
     "keys": ("desert", "sand", "dune", "canyon", "arid", "mesa", "wasteland", "dust")},
    {"name": "sunken depths", "structure": [0.26, 0.55, 0.62], "sun": [0.6, 0.85, 1.0],
     "intensity": 4.5, "pitch": -38.0, "fog": 0.07, "character": [0.30, 0.70, 0.78],
     "keys": ("ocean", "underwater", "sunken", "aquatic", "reef", "abyss", "sea", "tidal")},
    {"name": "neon night", "structure": [0.20, 0.20, 0.30], "sun": [0.45, 0.5, 0.85],
     "intensity": 3.0, "pitch": -55.0, "fog": 0.06, "character": [0.35, 0.9, 0.95],
     "keys": ("neon", "cyber", "synthwave", "futurist", "sci-fi", "scifi", "space", "station",
              "galaxy", "robot", "android")},
    {"name": "haunted ruins", "structure": [0.26, 0.23, 0.32], "sun": [0.5, 0.46, 0.62],
     "intensity": 3.5, "pitch": -24.0, "fog": 0.075, "character": [0.62, 0.50, 0.72],
     "keys": ("haunted", "spooky", "ghost", "graveyard", "horror", "cursed", "crypt", "nightmare",
              "gothic")},
)
_NEUTRAL_THEME = {
    "name": "stone ruins", "structure": [0.55, 0.50, 0.45], "sun": [1.0, 0.95, 0.85],
    "intensity": 6.0, "pitch": -45.0, "fog": 0.02, "character": [0.60, 0.60, 0.65],
}
# Fixed, readable accents for gameplay roles (kept across themes so the level stays legible).
_ROLE_ACCENT = {
    "hazard": [0.95, 0.12, 0.06],
    "collectible": [1.0, 0.80, 0.12],
    "goal": [0.12, 0.95, 0.5],
}


def _theme_palette(text: str) -> dict:
    """Match a theme palette from prompt/theme keywords; neutral stone ruins if nothing matches."""
    t = (text or "").lower()
    for theme in _THEMES:
        if any(k in t for k in theme["keys"]):
            return theme
    return _NEUTRAL_THEME


def apply_theme(spec: dict, text: str) -> dict:
    """Stamp a consistent theme onto a dressing from the prompt: structure/role colours, lighting,
    fog, and the character tint — so e.g. a 'frozen' prompt is always icy, even on a weak LLM plan.
    """
    p = _theme_palette(text)
    s = p["structure"]
    spec["palette"] = {
        "platform": [min(1.0, c * 1.25) for c in s],
        "obstacle": [c * 0.5 for c in s],
        "cover": s,
        "prop": s,
        **_ROLE_ACCENT,
    }
    spec["sun"] = {"color": list(p["sun"]), "intensity": p["intensity"], "pitch": p["pitch"]}
    spec["fog"] = p["fog"]
    char = spec.get("character") if isinstance(spec.get("character"), dict) else {}
    char = {"prefer": char.get("prefer", ""), "tint": list(p["character"])}
    spec["character"] = char
    if not spec.get("theme") or spec["theme"] == default_dressing()["theme"]:
        spec["theme"] = p["name"]
    return spec


def apply_pack(spec: dict, pack: assetpacks.AssetPack) -> dict:
    """Bind every placement to a REAL asset from the pack (by role) and set ground + tint flag.

    With a real Megascans/Fab pack each placement gets an ``asset`` (a content-path mesh) that the
    dress script spawns *with its own photoreal material* (no role tint), and the floor gets the
    pack's ground surface. With the builtin prototype pack, ``tint_objects`` stays on so the grey
    shapes are role-coloured as before. The director's layout (zones/positions/scale) is unchanged —
    only what's *placed* gets better.
    """
    counters: dict[str, int] = {}
    for p in spec.get("placements") or []:
        assets = pack.assets_for(p.get("role", "prop"))
        if assets:
            i = counters.get(p["role"] if p.get("role") else "prop", 0)
            p["asset"] = assets[i % len(assets)]
            counters[p.get("role", "prop")] = i + 1
    spec["pack_source"] = pack.source
    spec["tint_objects"] = not pack.is_real  # real assets keep materials; only proto is tinted
    if pack.ground_material:
        spec["ground_material"] = pack.ground_material
    return spec


def default_dressing() -> dict:
    """A safe, playable dressing when no LLM spec is available: a short obstacle course + a goal."""
    return {
        "title": "Prototype Course",
        "theme": "prototype course",
        "objective": "Reach the target at the far end of the course.",
        # Player-character look (applied to the template's pawn): an optional mesh-variant
        # preference (matched against whatever ships in the clone) + a theme accent tint.
        "character": {"prefer": "", "tint": [0.6, 0.6, 0.65]},
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
    char = spec.get("character")
    if isinstance(char, dict):
        prefer = char.get("prefer")
        out["character"]["prefer"] = prefer.strip()[:40] if isinstance(prefer, str) else ""
        tint = char.get("tint")
        if isinstance(tint, list) and len(tint) == 3:
            out["character"]["tint"] = [_num(c, 0.0, 1.0, 0.6) for c in tint]
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
    theme_text = " ".join(
        [prompt, (hints or {}).get("theme", ""), (hints or {}).get("vibe", "")]
    )
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
                return apply_theme(spec, theme_text)
    except Exception:  # noqa: BLE001 - direction must never break a build
        pass
    return apply_theme(out, theme_text)


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
        # generous scales so objects read at a distance and fill the playfield (not tiny specks)
        placements.append(_place(kind, x, y, z, role, sx=2.4, sy=2.4, sz=1.5 + (k % 3)))
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
    theme_text = " ".join([prompt, (hints or {}).get("theme", ""), (hints or {}).get("vibe", "")])
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
                    return apply_theme(improved, theme_text)
    except Exception:  # noqa: BLE001 - improvement must never break a build
        pass
    return apply_theme(_augment(spec, size=size), theme_text)


# Per-role object colours (RGB 0..1) — turns the grey LevelPrototyping meshes into a readable,
# themed level (hazards red, collectibles gold, the goal bright), the #1 "make it look real" lever.
_ROLE_COLOR: dict[str, list[float]] = {
    "platform": [0.78, 0.50, 0.28],   # warm stone/orange — reads as a step you can climb
    "obstacle": [0.16, 0.17, 0.22],   # near-black charcoal
    "cover": [0.28, 0.40, 0.62],      # slate blue
    "hazard": [0.95, 0.11, 0.05],     # bright danger red
    "collectible": [1.00, 0.78, 0.10],# gold
    "goal": [0.10, 0.95, 0.45],       # bright green — the place to reach
    "prop": [0.55, 0.50, 0.46],
}


def dress_level_script(spec: dict, map_path: str) -> str:
    """UE Python that loads the template level and ADDS the dressing, then writes PLAYSMITH_ASSERT.

    Additive on the real template level (loads, never new_level). Static meshes go on actors;
    palette Blueprints (jump pad, target, door) are spawned by class. Each gets its role as a tag so
    later steps (and the critic) can reason about it. Results come back via ``$PLAYSMITH_UE_OUT``.
    """
    spec_json = json.dumps(spec)
    palette_json = json.dumps(PALETTE)
    # Theme-derived per-role colours (apply_theme set spec["palette"]); fall back to the static map.
    role_color_json = json.dumps(spec.get("palette") or _ROLE_COLOR)
    return (
        "import json, os\n"
        "import unreal\n"
        f'MAP = "{map_path}"\n'
        f"SPEC = json.loads(r'''{spec_json}''')\n"
        f"PALETTE = json.loads(r'''{palette_json}''')\n"
        f"ROLE_COLOR = json.loads(r'''{role_color_json}''')\n"
        'PROP_DEST = "/Game/Playsmith/Props"\n'
        # Real Megascans/Fab meshes keep their photoreal materials (TINT off); the prototype
        # fallback is role-coloured (TINT on). GROUND_MATERIAL is an optional surface for the floor.
        "TINT = SPEC.get('tint_objects', True)\n"
        "GROUND_MATERIAL = SPEC.get('ground_material')\n"
        'OUT = os.environ.get("PLAYSMITH_UE_OUT", "")\n'
        # A shared param material + one MaterialInstanceConstant per role, so placed meshes are
        # coloured by role (themed + readable) instead of all grey. Cached; persists on save.
        "_mic_cache = {}\n"
        "def _prop_base():\n"
        "    p = PROP_DEST + '/M_PS_Props'\n"
        "    if unreal.EditorAssetLibrary.does_asset_exist(p):\n"
        "        return unreal.EditorAssetLibrary.load_asset(p)\n"
        "    tools = unreal.AssetToolsHelpers.get_asset_tools()\n"
        "    m = tools.create_asset('M_PS_Props', PROP_DEST, "
        "unreal.Material, unreal.MaterialFactoryNew())\n"
        "    vp = unreal.MaterialEditingLibrary.create_material_expression("
        "m, unreal.MaterialExpressionVectorParameter, -350, 0)\n"
        "    vp.set_editor_property('parameter_name', 'TintColor')\n"
        "    vp.set_editor_property('default_value', unreal.LinearColor(0.5, 0.5, 0.5, 1.0))\n"
        "    unreal.MaterialEditingLibrary.connect_material_property("
        "vp, '', unreal.MaterialProperty.MP_BASE_COLOR)\n"
        "    unreal.MaterialEditingLibrary.recompile_material(m)\n"
        "    return m\n"
        "def _role_mic(role):\n"
        "    if role in _mic_cache:\n"
        "        return _mic_cache[role]\n"
        "    mic = None\n"
        "    try:\n"
        "        c = ROLE_COLOR.get(role) or ROLE_COLOR.get('prop') or [0.5, 0.45, 0.44]\n"
        "        tools = unreal.AssetToolsHelpers.get_asset_tools()\n"
        "        p = PROP_DEST + '/MI_PS_' + role\n"
        "        if unreal.EditorAssetLibrary.does_asset_exist(p):\n"
        "            mic = unreal.EditorAssetLibrary.load_asset(p)\n"
        "        else:\n"
        "            mic = tools.create_asset('MI_PS_' + role, PROP_DEST, "
        "unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())\n"
        "            _b = _prop_base()\n"
        "            unreal.MaterialEditingLibrary.set_material_instance_parent(mic, _b)\n"
        "        unreal.MaterialEditingLibrary.set_material_instance_vector_parameter_value("
        "mic, 'TintColor', unreal.LinearColor(float(c[0]), float(c[1]), float(c[2]), 1.0))\n"
        "    except Exception as e:\n"
        "        unreal.log_warning('PLAYSMITH prop tint skipped: %s' % e)\n"
        "        mic = None\n"
        "    _mic_cache[role] = mic\n"
        "    return mic\n"
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
        # Re-theme the template's OWN objects (its demo course) to the structure colour, so the
        # WHOLE level reads as the theme — every non-Playsmith StaticMeshActor, any mesh path.
        # (Only for the prototype path; with real assets the template demo isn't grey-tinted.)
        "_struct = _role_mic('cover') if TINT else None\n"
        "if _struct is not None:\n"
        "    for _ta in eas.get_all_level_actors():\n"
        "        try:\n"
        "            if not isinstance(_ta, unreal.StaticMeshActor):\n"
        "                continue\n"
        "            if _ta.get_actor_label().startswith('PS_'):\n"
        "                continue\n"
        "            _sc = _ta.static_mesh_component\n"
        "            if _sc.get_static_mesh() is None:\n"
        "                continue\n"
        "            for _i in range(max(1, _sc.get_num_materials())):\n"
        "                _sc.set_material(_i, _struct)\n"
        "        except Exception:\n"
        "            pass\n"
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
        "    _m = _role_mic(tag) if TINT else None\n"  # real assets keep their own material
        "    if _m is not None:\n"
        "        try:\n"
        "            a.static_mesh_component.set_material(0, _m)\n"
        "        except Exception:\n"
        "            pass\n"
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
        "    role = p.get('role', 'prop')\n"
        "    asset = p.get('asset')\n"
        "    if asset:\n"
        "        kind_type, path = 'mesh', asset\n"  # a real mesh chosen by apply_pack
        "    else:\n"
        "        entry = PALETTE.get(p.get('kind'))\n"
        "        if not entry:\n"
        "            continue\n"
        "        kind_type, path = entry[0], entry[1]\n"
        "    label = 'PS_%s_%d' % (p.get('kind', 'asset'), i)\n"
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
        # Ground surface: lay the pack's floor material on the big flat meshes (the floor).
        "if GROUND_MATERIAL:\n"
        "    try:\n"
        "        _gm = unreal.EditorAssetLibrary.load_asset(GROUND_MATERIAL)\n"
        "        if _gm is not None:\n"
        "            for _fa in eas.get_all_level_actors():\n"
        "                try:\n"
        "                    if not isinstance(_fa, unreal.StaticMeshActor):\n"
        "                        continue\n"
        "                    if _fa.get_actor_label().startswith('PS_'):\n"
        "                        continue\n"
        "                    _s = _fa.get_actor_scale3d()\n"
        "                    if _s.x >= 5.0 or _s.y >= 5.0:  # a large flat ground mesh\n"
        "                        _fc = _fa.static_mesh_component\n"
        "                        for _j in range(max(1, _fc.get_num_materials())):\n"
        "                            _fc.set_material(_j, _gm)\n"
        "                except Exception:\n"
        "                    pass\n"
        "    except Exception as e:\n"
        "        unreal.log_warning('PLAYSMITH ground surface skipped: %s' % e)\n"
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


def character_script(spec: dict, character_bp: str, character_dir: str) -> str:
    """UE Python that customizes the template's player character from the dressing's ``character``.

    Defensive and asset-discovering (CLAUDE.md: never a bad ref): it *lists* the SkeletalMeshes that
    actually ship in this clone under ``character_dir``, optionally swaps to one whose name matches
    ``prefer``, and applies a theme-tinted override material to the character Blueprint's mesh — all
    wrapped in try/except so a customization never breaks a build. Writes ``character_customized``
    (+ ``character_mesh``) via ``$PLAYSMITH_UE_OUT``. Persists by compiling + saving the Blueprint.
    """
    char = spec.get("character") or {}
    char_json = json.dumps(
        {"prefer": char.get("prefer", ""), "tint": char.get("tint", [0.6, 0.6, 0.65])}
    )
    return (
        "import json, os\n"
        "import unreal\n"
        f'CHAR_BP = "{character_bp}"\n'
        f'CHAR_DIR = "{character_dir}"\n'
        f"CHAR = json.loads(r'''{char_json}''')\n"
        'OUT = os.environ.get("PLAYSMITH_UE_OUT", "")\n'
        'DEST = "/Game/Playsmith/Char"\n'
        "ok = False\n"
        "chosen = ''\n"
        "tinted = False\n"
        "t = CHAR.get('tint') or [0.6, 0.6, 0.65]\n"
        "col = unreal.LinearColor(float(t[0]), float(t[1]), float(t[2]), 1.0)\n"
        "tools = unreal.AssetToolsHelpers.get_asset_tools()\n"
        # All skeletal-mesh components on the character CDO. Critically, first-person templates show
        # the ARMS (Mesh1P), not the hidden third-person Mesh — so tint every skeletal mesh comp.
        # SubobjectDataSubsystem is the reliable way to reach a Blueprint's component TEMPLATES
        # headlessly — a CDO's get_editor_property/get_components_by_class return nothing in a
        # commandlet. Fall back to the CDO named props ('mesh'=3P body, 'mesh1p'=FP arms) if needed.
        "def _char_comps():\n"
        "    comps = []\n"
        "    bp = unreal.EditorAssetLibrary.load_asset(CHAR_BP)\n"
        "    try:\n"
        "        sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)\n"
        "        for h in sds.k2_gather_subobject_data_for_blueprint(bp):\n"
        "            try:\n"
        "                data = sds.k2_find_subobject_data_from_handle(h)\n"
        "                obj = unreal.SubobjectDataBlueprintFunctionLibrary.get_object(data)\n"
        "                if isinstance(obj, unreal.SkeletalMeshComponent) and obj not in comps:\n"
        "                    comps.append(obj)\n"
        "            except Exception:\n"
        "                pass\n"
        "    except Exception as e:\n"
        "        unreal.log_warning('PLAYSMITH subobject gather failed: %s' % e)\n"
        "    if not comps:\n"
        "        try:\n"
        "            gcls = unreal.EditorAssetLibrary.load_blueprint_class(CHAR_BP)\n"
        "            cdo = gcls.get_default_object() if gcls else None\n"
        "            for prop in ('mesh', 'mesh1p'):\n"
        "                try:\n"
        "                    c = cdo.get_editor_property(prop) if cdo else None\n"
        "                    if c is not None and c not in comps:\n"
        "                        comps.append(c)\n"
        "                except Exception:\n"
        "                    pass\n"
        "        except Exception:\n"
        "            pass\n"
        "    return bp, comps\n"
        # 1) optional mesh-variant swap from what actually ships in this clone (no bad refs)
        "try:\n"
        "    prefer = (CHAR.get('prefer') or '').lower()\n"
        "    if prefer:\n"
        "        cdo, comps = _char_comps()\n"
        "        pick = None\n"
        "        for ap in unreal.EditorAssetLibrary.list_assets(CHAR_DIR, recursive=True):\n"
        "            a = unreal.EditorAssetLibrary.load_asset(ap)\n"
        "            if isinstance(a, unreal.SkeletalMesh) and prefer in a.get_name().lower():\n"
        "                pick = a\n"
        "                break\n"
        "        if pick is not None and comps:\n"
        "            comps[0].set_skeletal_mesh_asset(pick)\n"
        "            chosen = pick.get_name()\n"
        "            ok = True\n"
        "except Exception as e:\n"
        "    unreal.log_warning('PLAYSMITH char mesh swap skipped: %s' % e)\n"
        # 2) theme tint via a MaterialInstanceConstant from a self-built param material (persists)
        "try:\n"
        "    base_path = DEST + '/M_PS_CharBase'\n"
        "    if unreal.EditorAssetLibrary.does_asset_exist(base_path):\n"
        "        base = unreal.EditorAssetLibrary.load_asset(base_path)\n"
        "    else:\n"
        "        base = tools.create_asset('M_PS_CharBase', DEST, unreal.Material, "
        "unreal.MaterialFactoryNew())\n"
        "        vp = unreal.MaterialEditingLibrary.create_material_expression(base, "
        "unreal.MaterialExpressionVectorParameter, -350, 0)\n"
        "        vp.set_editor_property('parameter_name', 'TintColor')\n"
        "        vp.set_editor_property('default_value', col)\n"
        "        unreal.MaterialEditingLibrary.connect_material_property(vp, '', "
        "unreal.MaterialProperty.MP_BASE_COLOR)\n"
        "        unreal.MaterialEditingLibrary.recompile_material(base)\n"
        "    mic_path = DEST + '/MI_PS_Char'\n"
        "    if unreal.EditorAssetLibrary.does_asset_exist(mic_path):\n"
        "        mic = unreal.EditorAssetLibrary.load_asset(mic_path)\n"
        "    else:\n"
        "        mic = tools.create_asset('MI_PS_Char', DEST, "
        "unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())\n"
        "        unreal.MaterialEditingLibrary.set_material_instance_parent(mic, base)\n"
        "    unreal.MaterialEditingLibrary.set_material_instance_vector_parameter_value("
        "mic, 'TintColor', col)\n"
        "    cdo, comps = _char_comps()\n"
        "    for comp in comps:\n"
        "        try:\n"
        "            cnt = comp.get_num_materials() if hasattr(comp, 'get_num_materials') else 1\n"
        "            for i in range(max(1, cnt)):\n"
        "                comp.set_material(i, mic)\n"
        "            tinted = True\n"
        "            ok = True\n"
        "        except Exception:\n"
        "            pass\n"
        "    unreal.EditorAssetLibrary.save_asset(base_path)\n"
        "    unreal.EditorAssetLibrary.save_asset(mic_path)\n"
        "except Exception as e:\n"
        "    unreal.log_warning('PLAYSMITH char tint skipped: %s' % e)\n"
        # 3) compile + save the character Blueprint so the override persists into PIE
        "try:\n"
        "    bp = unreal.EditorAssetLibrary.load_asset(CHAR_BP)\n"
        "    if bp is not None:\n"
        "        unreal.BlueprintEditorLibrary.compile_blueprint(bp)\n"
        "    unreal.EditorAssetLibrary.save_asset(CHAR_BP)\n"
        "except Exception as e:\n"
        "    unreal.log_warning('PLAYSMITH char save skipped: %s' % e)\n"
        "unreal.log('PLAYSMITH character mesh=%s tinted=%s' % (chosen or 'default', tinted))\n"
        "lines = [\n"
        "    'PLAYSMITH_ASSERT character_customized=%s' % ('true' if ok else 'false'),\n"
        "    'PLAYSMITH_ASSERT character_tinted=%s' % ('true' if tinted else 'false'),\n"
        "]\n"
        "if OUT:\n"
        "    with open(OUT, 'w') as f:\n"
        "        f.write('\\n'.join(lines) + '\\n')\n"
    )
