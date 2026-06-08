"""Tests for bring-your-own-art: the list_assets tool, goal wiring, and CLI import."""

from __future__ import annotations

from typer.testing import CliRunner

from playsmith.agent import AutoApprover, ToolContext, execute
from playsmith.cli.main import app
from playsmith.llm import ToolCall
from playsmith.studio import build_goal
from tests.conftest import FakeAdapter


def _ctx(tmp_path) -> ToolContext:
    return ToolContext(adapter=FakeAdapter(tmp_path / "game"), approver=AutoApprover())


def test_list_assets_tool_finds_imported_art(tmp_path) -> None:
    ctx = _ctx(tmp_path)
    (ctx.workspace / "assets").mkdir(parents=True)
    (ctx.workspace / "assets" / "cat.png").write_bytes(b"\x89PNG")
    (ctx.workspace / "_playsmith_screenshot.png").write_bytes(b"x")  # harness file, ignored
    msg = execute(ToolCall(id="1", name="list_assets", arguments={}), ctx)
    assert "res://assets/cat.png" in msg
    assert "_playsmith_screenshot" not in msg


def test_list_assets_tool_empty_suggests_placeholders(tmp_path) -> None:
    msg = execute(ToolCall(id="1", name="list_assets", arguments={}), _ctx(tmp_path))
    assert "placeholder" in msg.lower()


def test_build_goal_mentions_imported_art(tmp_path) -> None:
    project = tmp_path / "g"
    (project / "assets").mkdir(parents=True)
    (project / "assets" / "hero.png").write_bytes(b"\x89PNG")
    goal = build_goal("a platformer", None, project)
    assert "IMPORTED ART" in goal
    assert "res://assets/hero.png" in goal


def test_cli_assets_import_copies_into_project(tmp_path) -> None:
    project = tmp_path / "game"
    project.mkdir()
    (project / "project.godot").write_text("x")
    src = tmp_path / "cat.png"
    src.write_bytes(b"\x89PNG\r\n")

    result = CliRunner().invoke(app, ["assets", "import", str(src), "--project", str(project)])
    assert result.exit_code == 0, result.output
    assert (project / "assets" / "cat.png").read_bytes() == b"\x89PNG\r\n"


def test_cli_assets_import_rejects_missing_file(tmp_path) -> None:
    project = tmp_path / "game"
    project.mkdir()
    (project / "project.godot").write_text("x")
    result = CliRunner().invoke(
        app, ["assets", "import", str(tmp_path / "nope.png"), "--project", str(project)]
    )
    assert result.exit_code == 1
