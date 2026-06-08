"""LLM-driven level direction for Unreal — a per-game level spec from a plain prompt.

The Unreal analog of the 2D art director: ask the LLM for a themed level layout (lighting mood +
obstacle placement + goal) so every Unreal game is different, then hand it to
:func:`playsmith.engines.unreal.templates.build_level_script`. Always optional — any failure falls
back to a safe default level and never blocks a build.
"""

from __future__ import annotations

import json
import re

from playsmith.engines.unreal import templates
from playsmith.llm import LLMGateway, Message

_SYSTEM = "You are a 3D level designer. Reply with STRICT JSON only — no prose, no code fences."

# UE units are centimetres; keep the playfield bounded and reachable.
_BOUND_XY = 2500.0
_BOUND_Z = 600.0


def _ask(prompt: str) -> str:
    return (
        "Design a small, playable 3D level for this game, themed to it.\n\n"
        f"GAME: {prompt}\n\n"
        "Return STRICT JSON exactly like:\n"
        "{\n"
        '  "theme": "<short theme>",\n'
        '  "sun": {"color": [r,g,b], "intensity": <2-10>, "pitch": <-80..-10>},\n'
        '  "fog": <0.0-0.1>,\n'
        '  "obstacles": [{"x":<-2000..2000>,"y":<-2000..2000>,"z":<50..400>,'
        '"sx":<1-5>,"sy":<1-5>,"sz":<1-6>}, ...],\n'
        '  "goal": {"x":<-2000..2000>,"y":<-2000..2000>,"z":<50..400>}\n'
        "}\n"
        "Colour components are 0..1. Use 4-10 obstacles laid out as an interesting path from the "
        "player start toward the goal. Make the lighting/fog match the game's mood."
    )


def _num(value, lo: float, hi: float, default: float) -> float:
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return default


def _sanitize(spec: dict) -> dict:
    """Clamp everything to safe, reachable ranges so a bad LLM spec can't break the level."""
    out = templates.default_spec()
    if isinstance(spec.get("theme"), str) and spec["theme"].strip():
        out["theme"] = spec["theme"].strip()[:60]
    sun = spec.get("sun") or {}
    color = sun.get("color")
    if isinstance(color, list) and len(color) == 3:
        out["sun"]["color"] = [_num(c, 0.0, 1.0, 1.0) for c in color]
    out["sun"]["intensity"] = _num(sun.get("intensity"), 1.0, 12.0, 6.0)
    out["sun"]["pitch"] = _num(sun.get("pitch"), -85.0, -5.0, -45.0)
    out["fog"] = _num(spec.get("fog"), 0.0, 0.1, 0.02)
    obstacles = spec.get("obstacles")
    if isinstance(obstacles, list) and obstacles:
        clean = []
        for o in obstacles[:12]:
            if not isinstance(o, dict):
                continue
            clean.append(
                {
                    "x": _num(o.get("x"), -_BOUND_XY, _BOUND_XY, 0.0),
                    "y": _num(o.get("y"), -_BOUND_XY, _BOUND_XY, 0.0),
                    "z": _num(o.get("z"), 50.0, _BOUND_Z, 100.0),
                    "sx": _num(o.get("sx"), 0.5, 6.0, 2.0),
                    "sy": _num(o.get("sy"), 0.5, 6.0, 2.0),
                    "sz": _num(o.get("sz"), 0.5, 8.0, 2.0),
                }
            )
        if clean:
            out["obstacles"] = clean
    goal = spec.get("goal")
    if isinstance(goal, dict):
        out["goal"] = {
            "x": _num(goal.get("x"), -_BOUND_XY, _BOUND_XY, 1700.0),
            "y": _num(goal.get("y"), -_BOUND_XY, _BOUND_XY, 0.0),
            "z": _num(goal.get("z"), 50.0, _BOUND_Z, 150.0),
        }
    return out


def plan_level(prompt: str, gateway: LLMGateway) -> dict:
    """Ask the LLM for a themed level spec; fall back to the default level on any failure."""
    try:
        resp = gateway.chat([Message.system(_SYSTEM), Message.user(_ask(prompt))])
        match = re.search(r"\{.*\}", resp.content or "", re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return _sanitize(parsed)
    except Exception:  # noqa: BLE001 - level direction must never break a build
        pass
    return templates.default_spec()
