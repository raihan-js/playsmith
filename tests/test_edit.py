"""Tests for `playsmith edit` (natural-language iteration) and the project manifest."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from playsmith.agent import AutoApprover
from playsmith.cli.main import app
from playsmith.config import Config
from playsmith.engines.base import EngineError
from playsmith.studio import build_edit_goal, edit_game, read_manifest, write_manifest
from tests.conftest import FakeAdapter, FakeGateway, tool_response


def test_manifest_roundtrip(tmp_path) -> None:
    write_manifest(tmp_path, skill="2d-platformer", prompt="a cat game", assertions=["no_errors"])
    data = read_manifest(tmp_path)
    assert data == {"skill": "2d-platformer", "prompt": "a cat game", "assertions": ["no_errors"]}
    assert read_manifest(tmp_path / "elsewhere") is None


def test_edit_game_reads_understands_patches_and_verifies(tmp_path) -> None:
    adapter = FakeAdapter(tmp_path / "game")
    (adapter.project_dir / "project.godot").write_text('config/name="G"\n')
    (adapter.project_dir / "scripts").mkdir()
    (adapter.project_dir / "scripts" / "player.gd").write_text("var jump = 220.0\n")
    write_manifest(
        adapter.project_dir, skill="2d-platformer", prompt="cat", assertions=["player_on_floor"]
    )

    gateway = FakeGateway(
        [
            tool_response("read_file", {"path": "scripts/player.gd"}, call_id="c1"),
            tool_response(
                "apply_patch",
                {"path": "scripts/player.gd", "find": "220.0", "replace": "400.0"},
                call_id="c2",
            ),
            tool_response("run_engine", {}, call_id="c3"),
            tool_response("verify_game", {}, call_id="c4"),
            tool_response("task_complete", {"summary": "raised jump"}, call_id="c5"),
        ]
    )

    outcome = edit_game(
        "make the player jump higher",
        config=Config(),
        gateway=gateway,
        adapter=adapter,
        approver=AutoApprover(),
        verbose=False,
    )

    assert outcome.agent_result.done
    assert outcome.skill_name == "2d-platformer"  # recovered from the manifest
    assert "400.0" in (adapter.project_dir / "scripts" / "player.gd").read_text()
    assert adapter.verifies >= 1
    assert outcome.runs_clean


def test_edit_goal_mentions_change_and_assertions(tmp_path) -> None:
    goal = build_edit_goal("add a second platform", tmp_path, ["player_on_floor", "no_errors"])
    assert "add a second platform" in goal
    assert "EXISTING Godot 4 project" in goal
    assert "player_on_floor" in goal


def test_edit_game_without_project_raises(tmp_path) -> None:
    cfg = Config(workspace_dir=tmp_path / "empty")
    with pytest.raises(EngineError):
        edit_game("change something", config=cfg, verbose=False)


def test_cli_edit_errors_without_project(tmp_path) -> None:
    result = CliRunner().invoke(app, ["edit", "make it red", "--project", str(tmp_path / "nope")])
    assert result.exit_code == 1
