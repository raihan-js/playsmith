"""Contextual, step-by-step art direction.

Instead of one generic background for every game, the art director asks the LLM for an art plan
specific to THIS game (style, palette, and which elements to draw), then generates each asset one
at a time. Every game ends up looking different and on-theme. Art is always optional — any failure
degrades to placeholders and never blocks a build.

The generated files are named after game *slots* (``background.png``, ``player.png``,
``coin.png``, ``spike.png``, ``goal.png``) so the skill's ``game.gd`` can load+apply them at
runtime without any brittle scene edits.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

from playsmith.llm import LLMGateway, Message

# Slots a skill's game.gd knows how to apply at runtime. Background + player are universal.
PLATFORMER_SLOTS = ["background", "player", "coin", "spike", "goal"]

_SYSTEM = "You are a game art director. Reply with STRICT JSON only — no prose, no code fences."


def _ask_prompt(game_prompt: str, genre: str, slots: list[str]) -> str:
    return (
        "Design the art for a 2D game so it looks unique and strongly on-theme.\n\n"
        f"GAME IDEA: {game_prompt}\n"
        f"GENRE: {genre}\n\n"
        "Return STRICT JSON in exactly this shape:\n"
        '{\n'
        '  "style": "<one short line: art style + palette, e.g. \'moody pixel art, '
        "teal and magenta neon'>\",\n"
        '  "assets": [\n'
        '    {"slot": "background", "prompt": "<vivid scene art, NO text, '
        'NO UI, NO characters>"},\n'
        '    {"slot": "player", "prompt": "<the main character as a single sprite, side view, '
        'centered, plain flat background>"}\n'
        "  ]\n"
        "}\n\n"
        f"Allowed slots: {', '.join(slots)}. ALWAYS include background and player. Add coin/spike/"
        "goal ONLY if they suit this game. 2 to 4 assets total. Each prompt must be specific to "
        "THIS game's subject, mood and colors — not generic."
    )


def _extract_json(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _fallback(game_prompt: str) -> dict:
    """A safe plan when the LLM is unavailable: a themed background + player from the raw prompt."""
    return {
        "style": "cohesive game art",
        "assets": [
            {"slot": "background", "prompt": f"game background for: {game_prompt}"},
            {"slot": "player", "prompt": f"main character sprite for: {game_prompt}, side view"},
        ],
    }


def plan_art(
    game_prompt: str,
    genre: str,
    gateway: LLMGateway,
    *,
    slots: list[str] | None = None,
    max_assets: int = 4,
) -> dict:
    """Ask the LLM for a contextual art plan; fall back to a generic one on any failure."""
    slots = slots or PLATFORMER_SLOTS
    spec: dict | None = None
    try:
        resp = gateway.chat(
            [Message.system(_SYSTEM), Message.user(_ask_prompt(game_prompt, genre, slots))]
        )
        spec = _extract_json(resp.content or "")
    except Exception:  # noqa: BLE001 - art planning must never break a build
        spec = None
    if not spec or not isinstance(spec.get("assets"), list):
        spec = _fallback(game_prompt)

    # Sanitize: keep known slots, dedupe, guarantee background + player, cap the count.
    seen: set[str] = set()
    clean: list[dict] = []
    for asset in spec["assets"]:
        if not isinstance(asset, dict):
            continue
        slot = str(asset.get("slot", "")).strip().lower()
        prompt = str(asset.get("prompt", "")).strip()
        if slot in slots and slot not in seen and prompt:
            seen.add(slot)
            clean.append({"slot": slot, "prompt": prompt})
    for required in ("background", "player"):
        if required not in seen:
            fb = _fallback(game_prompt)["assets"]
            clean.append(next(a for a in fb if a["slot"] == required))
            seen.add(required)
    # background first (it imports/applies as the backdrop), then the rest.
    clean.sort(key=lambda a: 0 if a["slot"] == "background" else 1)
    return {"style": str(spec.get("style", "")).strip(), "assets": clean[:max_assets]}


def generate_art(
    spec: dict,
    asset_gen,
    adapter,
    *,
    emit: Callable[[dict], None] | None = None,
    log: Callable[[str], None] | None = None,
) -> list[str]:
    """Generate each planned asset one at a time, streaming progress; import once at the end.

    Returns the list of slots produced. Each asset's prompt is fused with the global style so the
    set looks cohesive. Sprites get transparent backgrounds via the image backend (kind=sprite).
    """
    style = spec.get("style", "")
    project_dir = Path(adapter.project_dir)
    produced: list[str] = []
    for asset in spec.get("assets", []):
        slot = asset["slot"]
        kind = "background" if slot == "background" else "sprite"
        full_prompt = f"{asset['prompt']}. Art style: {style}." if style else asset["prompt"]
        out = project_dir / "assets" / f"{slot}.png"
        if emit is not None:
            emit({"type": "phase", "text": f"Generating {slot} art"})
        try:
            asset_gen.image(full_prompt, kind, str(out))
            produced.append(slot)
            if emit is not None:
                emit({"type": "observe", "name": "generate_asset",
                      "text": f"saved assets/{slot}.png", "ok": True})
            if log is not None:
                log(f"Generated {slot} art")
        except Exception:  # noqa: BLE001 - skip a failed asset, keep going
            if emit is not None:
                emit({"type": "observe", "name": "generate_asset",
                      "text": f"skipped {slot} (generation failed)"})
    if produced:
        try:
            adapter.import_assets()
        except Exception:  # noqa: BLE001 - import failure just means placeholders are used
            pass
    return produced
