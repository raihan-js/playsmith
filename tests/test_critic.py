"""Tests for the Critic — deterministic rubric scoring + actionable feedback. No Unreal needed."""

from __future__ import annotations

from playsmith.engines.unreal import critic, director


def test_sparse_default_does_not_pass_and_gives_feedback() -> None:
    c = critic.critique(director.default_dressing(), size="medium")
    assert not c.passed  # a sparse level can't pass — the density floor blocks it
    assert c.dimensions["density"] < critic._DENSITY_FLOOR
    assert c.feedback  # tells the director what to add
    assert "Quality" in c.summary


def test_rich_spread_level_scores_higher_than_sparse_and_passes() -> None:
    sparse = critic.critique(director.default_dressing(), size="medium").score
    rich = director._augment(director.default_dressing(), size="large")
    crich = critic.critique(rich, {"objects_placed": True, "goal_exists": True}, size="large")
    assert crich.score > sparse and crich.passed


def test_zones_dimension_rewards_multiple_areas() -> None:
    one_area = {"placements": [{"kind": "cube", "x": 100 + i, "y": 0, "z": 50, "role": "obstacle"}
                              for i in range(8)]}
    spread = director._augment(director.default_dressing(), size="large")
    assert (
        critic.critique(spread, size="large").dimensions["zones"]
        > critic.critique(one_area, size="large").dimensions["zones"]
    )


def test_engine_assertions_gate_the_score() -> None:
    spec = director._augment(director.default_dressing(), size="medium")
    good = critic.critique(spec, {"level_loads": True, "objects_placed": True, "goal_exists": True})
    bad = critic.critique(spec, {"level_loads": False, "objects_placed": True, "goal_exists": True})
    assert bad.score < good.score
    assert not bad.passed
    assert any("load" in f.lower() for f in bad.feedback)


def test_objects_not_placed_zeroes_density() -> None:
    spec = director._augment(director.default_dressing(), size="medium")
    c = critic.critique(spec, {"objects_placed": False})
    assert c.dimensions["density"] == 0.0 and not c.passed


def test_target_count_by_size() -> None:
    assert critic.target_count("small") < critic.target_count("large")
    assert critic.target_count(None) == critic.target_count("medium")


def test_score_render_seam_returns_none() -> None:
    assert critic.score_render("x.png", director.default_dressing(), object()) is None
