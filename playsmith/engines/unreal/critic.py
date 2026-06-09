"""The Critic — score a dressed level against a quality rubric and say what to improve.

CLAUDE.md §0/§4: structural asserts prove a level *runs*; the critic drives whether it's *good*.
This is the headless, **deterministic** half of the loop — it scores the director's dressing spec
(object density, variety, spread, verticality, flow, a real goal, lighting) plus the in-engine
``PLAYSMITH_ASSERT`` reality signals, so the director→critic loop runs anywhere with no vision
model. Scoring a real rendered screenshot with a vision model is a future addition; the seam is
:func:`score_render`. The critic returns a 0–100 score and *concrete, actionable* feedback the
director feeds back in to make the next pass better — the engine behind "more iterations".
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# A "good enough to ship a slice" target. The loop iterates until a dressing clears this.
DEFAULT_TARGET_SCORE = 70

# How many gameplay objects a level of each size should have (the density the critic drives toward).
_TARGET_BY_SIZE = {"small": 10, "medium": 18, "large": 28}

# Rubric weights (sum to 1.0). Density dominates — a sparse level is the #1 failure mode of a
# single dressing pass (the "very basic" first-person game the user hit), and a few well-placed
# objects shouldn't be able to "pass" on spread/lighting alone (see the density floor below).
_WEIGHTS = {
    "density": 0.30,
    "variety": 0.20,
    "spread": 0.14,
    "verticality": 0.12,
    "flow": 0.08,
    "goal": 0.10,
    "lighting": 0.06,
}

# A level must have real content to pass, not just be well-spread: density must clear this floor.
_DENSITY_FLOOR = 0.55

_TIPS = {
    "density": "Add more gameplay objects — the level feels sparse and empty.",
    "variety": "Use more object types and roles (cover, hazards, collectibles, platforms).",
    "spread": "Spread objects across the playfield — they're bunched up near the start.",
    "verticality": "Add platforms at varied heights so there's vertical interest to navigate.",
    "flow": "Build a clear route from the start toward the goal, not a flat scatter.",
    "goal": "Place exactly one clear goal, set well away from the player start.",
    "lighting": "Set a stronger lighting mood (sun intensity/colour) to match the theme.",
}


@dataclass
class Critique:
    """A critic's verdict on one dressing: a score, a pass/fail, and what to fix next."""

    score: int  # 0..100
    passed: bool
    dimensions: dict[str, float] = field(default_factory=dict)  # name -> 0..1 subscore
    feedback: list[str] = field(default_factory=list)  # concrete, ordered weakest-first
    summary: str = ""


def target_count(size: str | None) -> int:
    """The object-count target for a level size hint (defaults to medium)."""
    return _TARGET_BY_SIZE.get((size or "medium").lower(), _TARGET_BY_SIZE["medium"])


def _dimensions(spec: dict, size: str | None) -> dict[str, float]:
    placements = spec.get("placements") or []
    n = len(placements)
    target_n = target_count(size)
    kinds = {p.get("kind") for p in placements}
    roles = {p.get("role") for p in placements}
    dists = [math.hypot(p.get("x", 0) or 0, p.get("y", 0) or 0) for p in placements] or [0.0]
    z_levels = {round((p.get("z", 0) or 0) / 100) for p in placements}
    goals = [p for p in placements if p.get("role") == "goal"]
    sun = spec.get("sun") or {}

    max_dist = max(dists)
    far = sum(1 for d in dists if d > 800)
    if goals:
        gd = math.hypot(goals[0].get("x", 0) or 0, goals[0].get("y", 0) or 0)
        goal_score = 1.0 if (len(goals) == 1 and gd > 800) else 0.6
    else:
        goal_score = 0.0
    try:
        intensity = float(sun.get("intensity", 0) or 0)
    except (TypeError, ValueError):
        intensity = 0.0

    return {
        "density": min(1.0, n / target_n) if target_n else 0.0,
        "variety": min(1.0, (len(kinds) + len(roles)) / 10),
        "spread": min(1.0, max_dist / 2500),
        "verticality": min(1.0, len(z_levels) / 4),
        "flow": min(1.0, far / max(1.0, n * 0.6)),
        "goal": goal_score,
        "lighting": 1.0 if 1.0 <= intensity <= 12.0 else 0.4,
    }


def critique(
    spec: dict,
    assertions: dict | None = None,
    *,
    size: str | None = None,
    target_score: int = DEFAULT_TARGET_SCORE,
) -> Critique:
    """Score a dressing spec (+ optional in-engine ``PLAYSMITH_ASSERT`` results) 0–100.

    ``assertions`` are the engine's reality check (``level_loads``, ``objects_placed``,
    ``goal_exists``); when present they gate the matching rubric dimensions so the score reflects
    what actually happened in UE, not just the plan. Returns weakest-first, actionable feedback.
    """
    dims = _dimensions(spec, size)

    # Reality gates: let the engine's truth override the plan's optimism.
    if assertions is not None:
        if assertions.get("objects_placed") is False:
            dims["density"] = 0.0
        if assertions.get("goal_exists") is False:
            dims["goal"] = 0.0
    level_failed = assertions is not None and assertions.get("level_loads") is False

    score = round(100 * sum(_WEIGHTS[k] * v for k, v in dims.items()))
    if level_failed:
        score = min(score, 10)

    feedback = [
        _TIPS[name]
        for name, _ in sorted(dims.items(), key=lambda kv: kv[1])
        if dims[name] < 0.6
    ]
    passed = (
        score >= target_score
        and dims["goal"] > 0.0
        and dims["density"] >= _DENSITY_FLOOR  # enough real content, not just a few spread objects
        and not level_failed
    )
    if level_failed:
        feedback.insert(0, "The level failed to load in-engine — fix that before anything else.")
    summary = f"Quality {score}/100 — {'looks good' if passed else 'needs another pass'}."
    return Critique(
        score=score, passed=passed, dimensions=dims, feedback=feedback[:5], summary=summary
    )


def score_render(image_path: str, spec: dict, gateway: object) -> Critique | None:  # noqa: ARG001
    """Seam for a future vision critic: score a rendered screenshot with a vision model.

    Not wired yet (the gateway is text-only today). Returns ``None`` so callers fall back to the
    deterministic :func:`critique`. When vision lands, this scores framing/readability/content
    density from the actual frame and blends with the structural score.
    """
    return None
