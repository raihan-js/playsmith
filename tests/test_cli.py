"""CLI helper tests — notably that project names stay short enough for Unreal.

A too-long .uproject name segfaults UnrealEditor (it truncates the project name to ~63 chars, then
the filename no longer matches and it can't find the game directory). Keep both short.
"""

from __future__ import annotations

from types import SimpleNamespace

from typer.testing import CliRunner

from playsmith.cli.main import _proj_name, _slug, app


def test_cli_slug_truncates_long_prompts() -> None:
    long = "a third person game in a frozen ruined fortress climb icy platforms across a moat"
    assert _slug(long) == "a-third-person-game-in-a"  # first 6 words
    assert len(_slug(long)) <= 48
    assert _slug("") == "unreal-game"


def test_cli_proj_name_capped_well_under_ue_limit() -> None:
    assert _proj_name("a" * 300) == "a" * 40
    assert len(_proj_name("a really long frozen ruined fortress name " * 5)) <= 40
    assert _proj_name("") == "Game"


def _fake_cfg(workspace):
    return SimpleNamespace(
        workspace_dir=workspace,
        engine=SimpleNamespace(unreal=SimpleNamespace(editor_cmd="UnrealEditor-Cmd")),
    )


def test_unreal_serve_launches_editor_and_reports_on(tmp_path, monkeypatch) -> None:
    (tmp_path / "ws" / "myproj").mkdir(parents=True)
    cfg = _fake_cfg(tmp_path / "ws")
    monkeypatch.setattr("playsmith.cli.main.load_config", lambda *a, **k: cfg)

    state = {"n": 0, "launched": False}

    def avail():  # False on the pre-check, True once the editor's Remote Control is up
        state["n"] += 1
        return state["n"] > 1

    class _FakeAdapter:
        def __init__(self, *a, **k):
            self.remote = SimpleNamespace(available=avail, host="http://localhost:30010")

        def launch_editor(self, *, scene=None, render_offscreen=False):
            state["launched"] = True
            return 9999

    monkeypatch.setattr("playsmith.cli.main.UnrealAdapter", _FakeAdapter)
    result = CliRunner().invoke(app, ["unreal", "serve", "myproj"])
    assert result.exit_code == 0
    assert state["launched"] is True  # the editor was actually launched
    assert "Editor-in-the-loop ON" in result.stdout


def test_unreal_serve_errors_when_project_missing(tmp_path, monkeypatch) -> None:
    cfg = _fake_cfg(tmp_path / "ws")
    monkeypatch.setattr("playsmith.cli.main.load_config", lambda *a, **k: cfg)
    result = CliRunner().invoke(app, ["unreal", "serve", "ghost"])  # no such project
    assert result.exit_code == 1
    assert "No project at" in result.stdout
