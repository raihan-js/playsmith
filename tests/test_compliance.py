"""Tests for the compliance briefing + age-rating helpers (Phase 3 Step 5)."""

from __future__ import annotations

from typer.testing import CliRunner

from playsmith.cli.main import app
from playsmith.publish import age_rating, compliance_briefing


def test_briefing_per_target_selects_right_rules() -> None:
    steam = "\n".join(compliance_briefing("steam"))
    assert "AI-content disclosure" in steam
    assert "Apple" not in steam  # Apple rules don't apply to a Steam-only briefing

    apple = "\n".join(compliance_briefing("ios"))
    assert "4.2.6" in apple and "4.3" in apple

    google = "\n".join(compliance_briefing("android"))
    assert "repetitive content" in google


def test_briefing_all_includes_everything_and_caveats() -> None:
    notes = "\n".join(compliance_briefing("all"))
    assert "Apple" in notes and "Google" in notes and "AI-content disclosure" in notes
    assert "copyright protection" in notes  # AI-asset copyright caveat
    assert "mass-submit" in notes  # the discipline rule is always surfaced


def test_briefing_adds_unreal_royalty_when_used() -> None:
    assert any("royalty" in n for n in compliance_briefing("all", used_unreal=True))


def test_age_rating_defaults_to_everyone() -> None:
    assert age_rating()["rating"].startswith("Everyone")
    assert age_rating()["descriptors"] == []


def test_age_rating_high_violence_is_mature_with_descriptor() -> None:
    rating = age_rating(violence=3)
    assert rating["rating"].startswith("Mature")
    assert "Violence" in rating["descriptors"]


def test_age_rating_gambling_bumps_to_at_least_teen() -> None:
    rating = age_rating(gambling=True)
    assert "Teen" in rating["rating"] or "Mature" in rating["rating"]
    assert "Simulated Gambling" in rating["descriptors"]


def test_cli_publish_check_prints_briefing() -> None:
    result = CliRunner().invoke(app, ["publish", "--check"])
    assert result.exit_code == 0
    assert "Compliance briefing" in result.output
    assert "Age rating" in result.output
