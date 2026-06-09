"""Tests for the Critic — deterministic rubric scoring + actionable feedback. No Unreal needed."""

from __future__ import annotations

from playsmith.engines.unreal import critic, director


def test_sparse_default_scores_low_with_feedback() -> None:
    c = critic.critique(director.default_dressing(), size="medium")
    assert c.score < critic.DEFAULT_TARGET_SCORE
    assert not c.passed
    assert c.feedback  # tells the director what to add
    assert "Quality" in c.summary


def test_rich_spread_level_scores_higher_than_sparse() -> None:
    sparse = critic.critique(director.default_dressing(), size="medium").score
    rich = director._augment(director.default_dressing(), size="large")
    assert critic.critique(rich, size="large").score > sparse


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
