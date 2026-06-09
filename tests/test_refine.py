"""Tests for the director→critic refine loop — pure orchestration, fully faked. No Unreal."""

from __future__ import annotations

from playsmith.engines.unreal import refine
from playsmith.engines.unreal.critic import Critique


def _crit(score: int, passed: bool) -> Critique:
    return Critique(score=score, passed=passed, dimensions={}, feedback=["add more"], summary="s")


def test_loop_stops_early_when_critique_passes() -> None:
    events: list[dict] = []
    scores = iter([Critique(90, True, {}, [], "good")])
    result = refine.refine(
        plan=lambda: {"placements": [1, 2]},
        apply=lambda spec: {"level_loads": True},
        critique=lambda spec, a: next(scores),
        improve=lambda spec, c: spec,
        max_iters=3,
        on_event=events.append,
    )
    assert result.iterations == 1 and result.critique.passed
    kinds = [e["kind"] for e in events]
    assert kinds == ["planned", "applied", "critiqued"]  # no "improving" — it passed first try


def test_loop_iterates_and_improves_until_cap() -> None:
    crits = iter([_crit(40, False), _crit(55, False), _crit(60, False)])
    improved: list[int] = []

    def improve(spec, c):
        improved.append(c.score)
        return {"placements": spec["placements"] + [0]}

    result = refine.refine(
        plan=lambda: {"placements": [0]},
        apply=lambda spec: {"level_loads": True, "objects_placed": True},
        critique=lambda spec, a: next(crits),
        improve=improve,
        max_iters=3,
        on_event=lambda e: None,
    )
    assert result.iterations == 3  # ran the full budget since it never passed
    assert improved == [40, 55]  # improved after the 1st and 2nd, not after the final pass
    assert len(result.history) == 3 and result.critique.score == 60


def test_loop_clamps_iters_and_tolerates_no_on_event() -> None:
    result = refine.refine(
        plan=lambda: {"placements": []},
        apply=lambda spec: None,
        critique=lambda spec, a: _crit(10, False),
        improve=lambda spec, c: spec,
        max_iters=0,  # clamped up to 1
    )
    assert result.iterations == 1
