"""CLI helper tests — notably that project names stay short enough for Unreal.

A too-long .uproject name segfaults UnrealEditor (it truncates the project name to ~63 chars, then
the filename no longer matches and it can't find the game directory). Keep both short.
"""

from __future__ import annotations

from playsmith.cli.main import _proj_name, _slug


def test_cli_slug_truncates_long_prompts() -> None:
    long = "a third person game in a frozen ruined fortress climb icy platforms across a moat"
    assert _slug(long) == "a-third-person-game-in-a"  # first 6 words
    assert len(_slug(long)) <= 48
    assert _slug("") == "unreal-game"


def test_cli_proj_name_capped_well_under_ue_limit() -> None:
    assert _proj_name("a" * 300) == "a" * 40
    assert len(_proj_name("a really long frozen ruined fortress name " * 5)) <= 40
    assert _proj_name("") == "Game"
