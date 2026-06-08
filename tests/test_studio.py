"""End-to-end orchestration tests for `playsmith new` (gateway + engine mocked)."""

from __future__ import annotations

from playsmith.agent import AutoApprover
from playsmith.config import Config
from playsmith.skills import SkillLoader, SkillRouter
from playsmith.studio import build_goal, latest_project, new_game, slugify
from tests.conftest import FakeAdapter, FakeGateway, tool_response


def test_slugify() -> None:
    assert slugify("a 2D platformer where a cat collects fish!") == "a-2d-platformer-where-a-cat"
    assert slugify("") == "game"


def test_new_game_routes_scaffolds_generates_and_verifies(tmp_path) -> None:
    adapter = FakeAdapter(tmp_path / "catgame")
    gateway = FakeGateway(
        [
            tool_response(
                "write_file",
                {"path": "Main.tscn", "content": "[gd_scene format=3]\n"},
                call_id="c1",
            ),
            tool_response(
                "write_file",
                {"path": "scripts/player.gd", "content": "extends CharacterBody2D\n"},
                call_id="c2",
            ),
            tool_response("run_engine", {"headless": True}, call_id="c3"),
            tool_response(
                "task_complete", {"summary": "Platformer built and verified."}, call_id="c4"
            ),
        ]
    )

    outcome = new_game(
        "a 2D platformer where a cat collects fish",
        config=Config(),
        gateway=gateway,
        adapter=adapter,
        # Gateway-less router so the repo's two skills route by keyword, not by consuming
        # the scripted agent-loop responses above.
        router=SkillRouter(SkillLoader()),
        approver=AutoApprover(),
        verbose=False,
    )

    # Routed to the repo's only skill (single-skill shortcut).
    assert outcome.skill_name == "2d-platformer"
    # Scaffolding + agent-written files landed in the project.
    assert (adapter.project_dir / "project.godot").exists()
    assert (adapter.project_dir / "Main.tscn").exists()
    assert (adapter.project_dir / "scripts" / "player.gd").exists()
    # The deterministic starter scene was scaffolded (Player.tscn isn't written by the agent here).
    assert (adapter.project_dir / "Player.tscn").exists()
    # Agent finished and the final authoritative (assertion-based) verification was clean.
    assert outcome.agent_result.done
    assert outcome.runs_clean
    # The agent ran the engine, and studio ran the final verify() with the skill's assertions.
    assert adapter.runs >= 1
    assert adapter.verifies >= 1
    # A manifest was written so `playsmith edit` can verify this project later.
    from playsmith.studio import read_manifest

    assert read_manifest(adapter.project_dir)["skill"] == "2d-platformer"


def test_build_goal_with_scaffold_tells_agent_to_embellish(tmp_path) -> None:
    goal = build_goal("a cat platformer", None, tmp_path, ["Main.tscn", "scripts/player.gd"])
    assert "playable" in goal.lower()  # the base is already a complete playable game
    assert "do not rewrite" in goal.lower()
    assert "Main.tscn" in goal


def test_build_goal_includes_skill_body_and_player_template(tmp_path) -> None:
    from playsmith.skills import SkillLoader

    skill = SkillLoader().get("2d-platformer")
    goal = build_goal("a jumpy fox game", skill, tmp_path)
    assert "a jumpy fox game" in goal
    assert "2d-platformer" in goal
    assert "RUN AND VERIFY" in goal  # skill body
    assert "CharacterBody2D" in goal  # player.gd template injected
    assert str(tmp_path) in goal


def test_latest_project_picks_newest_and_ignores_engine_check(tmp_path) -> None:
    import os
    import time

    for i, name in enumerate(["_playsmith_engine_check", "old-game", "new-game"]):
        d = tmp_path / name
        d.mkdir()
        (d / "project.godot").write_text("x")
        # Stagger mtimes so 'new-game' is newest.
        os.utime(d, (time.time() + i, time.time() + i))

    latest = latest_project(tmp_path)
    assert latest is not None
    assert latest.name == "new-game"  # newest, and engine-check is excluded


def test_latest_project_none_when_empty(tmp_path) -> None:
    assert latest_project(tmp_path / "nope") is None
