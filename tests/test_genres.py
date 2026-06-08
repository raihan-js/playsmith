"""The builtin genre skills must load and declare only harness-checkable assertions.

These guard against shipping a genre whose verify assertions the engine can't actually evaluate
(which would make every build silently "fail" or fall back). Pure/offline — no Godot needed.
"""

from __future__ import annotations

from playsmith.assets.art_director import slots_for
from playsmith.engines.base import KNOWN_ASSERTIONS
from playsmith.skills import SkillLoader


def test_builtin_genres_present() -> None:
    names = {s.name for s in SkillLoader().discover()}
    assert {"2d-platformer", "space-shooter"} <= names


def test_every_genre_assertion_is_known() -> None:
    for skill in SkillLoader().discover():
        for assertion in skill.assertions:
            assert assertion in KNOWN_ASSERTIONS, (
                f"skill {skill.name!r} declares assertion {assertion!r} the harness can't check"
            )


def test_space_shooter_is_distinct_from_platformer() -> None:
    shooter = SkillLoader().get("space-shooter")
    assert shooter is not None
    # A shooter, not a reskinned platformer: spawns enemies, no floor/gravity assertions.
    assert "enemy_spawns" in shooter.assertions
    assert "player_on_floor" not in shooter.assertions
    assert slots_for("space-shooter") == ["background", "player", "enemy", "bullet"]
