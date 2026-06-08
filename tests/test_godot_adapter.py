"""Tests for the Godot adapter with the godot binary mocked (no Godot install needed)."""

from __future__ import annotations

import subprocess

import pytest

from playsmith.engines import (
    EngineError,
    EngineNotFoundError,
    ExportTarget,
    GodotAdapter,
    RunResult,
    SceneSpec,
)
from playsmith.engines.godot import templates


def _adapter(tmp_path) -> GodotAdapter:
    return GodotAdapter(tmp_path / "game", binary="godot")


# -- file authoring (no subprocess) ----------------------------------------------
def test_create_project_writes_godot4_project_file(tmp_path) -> None:
    a = _adapter(tmp_path)
    a.create_project("Cat Quest", main_scene="res://Main.tscn")
    proj = (a.project_dir / "project.godot").read_text()
    assert "config_version=5" in proj  # Godot 4, not 3.x
    assert 'config/name="Cat Quest"' in proj
    assert 'run/main_scene="res://Main.tscn"' in proj


def test_set_main_scene_updates_existing_line(tmp_path) -> None:
    a = _adapter(tmp_path)
    a.create_project("G", main_scene="res://Old.tscn")
    a.set_main_scene("res://New.tscn")
    proj = (a.project_dir / "project.godot").read_text()
    assert 'run/main_scene="res://New.tscn"' in proj
    assert "Old.tscn" not in proj


def test_set_main_scene_inserts_when_absent(tmp_path) -> None:
    a = _adapter(tmp_path)
    a.create_project("G")  # no main scene
    a.set_main_scene("res://Main.tscn")
    assert 'run/main_scene="res://Main.tscn"' in (a.project_dir / "project.godot").read_text()


def test_write_script_and_scene(tmp_path) -> None:
    a = _adapter(tmp_path)
    a.create_project("G")
    sp = a.write_script("scripts/player.gd", "extends CharacterBody2D\n")
    sc = a.write_scene(SceneSpec("Player.tscn", "[gd_scene format=3]\n"))
    assert sp.read_text().startswith("extends CharacterBody2D")
    assert sc.exists()
    assert sp.relative_to(a.project_dir)  # confined to project


def test_path_traversal_is_refused(tmp_path) -> None:
    a = _adapter(tmp_path)
    a.create_project("G")
    with pytest.raises(EngineError):
        a.write_script("../../escape.gd", "nope")


# -- process driving (subprocess mocked) -----------------------------------------
def test_run_builds_headless_command_and_parses_result(tmp_path, monkeypatch) -> None:
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["timeout"] = kwargs.get("timeout")
        return subprocess.CompletedProcess(cmd, 0, stdout="Godot Engine v4.3\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    a = _adapter(tmp_path)
    a.create_project("G", main_scene="res://Main.tscn")
    result = a.run(headless=True, timeout_s=30)

    assert isinstance(result, RunResult)
    assert result.ok
    assert "--headless" in captured["cmd"]
    assert "--path" in captured["cmd"]
    assert str(a.project_dir) in captured["cmd"]
    assert "--quit-after" in captured["cmd"]


def test_run_detects_script_errors_in_logs(tmp_path, monkeypatch) -> None:
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd, 0, stdout="", stderr="SCRIPT ERROR: Parse Error: Identifier not found\n"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    a = _adapter(tmp_path)
    a.create_project("G")
    result = a.run()
    assert not result.ok  # clean exit code but errors in logs
    assert any("SCRIPT ERROR" in line for line in result.error_lines())


def test_missing_binary_raises_engine_not_found(tmp_path, monkeypatch) -> None:
    def fake_run(cmd, **kwargs):
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(subprocess, "run", fake_run)
    a = _adapter(tmp_path)
    a.create_project("G")
    with pytest.raises(EngineNotFoundError):
        a.run()


def test_timeout_is_reported_not_raised(tmp_path, monkeypatch) -> None:
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 30), output="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    a = _adapter(tmp_path)
    a.create_project("G")
    result = a.run(timeout_s=5)
    assert result.timed_out
    assert not result.ok


def test_export_web_writes_preset_and_builds_command(tmp_path, monkeypatch) -> None:
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="exported", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    a = _adapter(tmp_path)
    a.create_project("G", main_scene="res://Main.tscn")
    out = tmp_path / "build" / "index.html"
    result = a.export(ExportTarget.WEB, str(out))
    assert result.returncode == 0
    assert (a.project_dir / "export_presets.cfg").exists()
    assert "--export-release" in captured["cmd"]
    assert "Web" in captured["cmd"]


def test_verify_harness_and_templates_support_3d() -> None:
    # The reality-loop harness must find 3D bodies too, and a 3D scene template must render.
    script = templates.verify_harness_script()
    assert "CharacterBody3D" in script
    assert "CharacterBody2D" in script  # still supports 2D
    assert "Node3D" in script
    assert "Camera3D" in templates.trivial_3d_scene()
    assert "Node3D" in templates.node3d_scene_with_script("Main", "res://m.gd")


def test_verify_parses_assertions_and_adds_no_errors(tmp_path, monkeypatch) -> None:
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env")
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=(
                "PLAYSMITH_ASSERT player_exists=true\n"
                "PLAYSMITH_ASSERT player_on_floor=true\n"
                "PLAYSMITH_ASSERT player_not_falling=false\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    a = _adapter(tmp_path)
    a.create_project("G", main_scene="res://Main.tscn")
    vr = a.verify(checks=["player_exists", "player_on_floor", "player_not_falling", "no_errors"])

    assert vr.assertions["player_exists"] is True
    assert vr.assertions["player_on_floor"] is True
    assert vr.assertions["player_not_falling"] is False
    assert vr.assertions["no_errors"] is True  # no error markers in the logs
    assert not vr.ok  # one assertion failed
    assert vr.failures() == ["player_not_falling"]
    # Harness was injected and run headless against the main scene.
    assert (a.project_dir / templates.VERIFY_SCRIPT).exists()
    assert "--headless" in captured["cmd"]
    assert captured["env"]["PLAYSMITH_TARGET_SCENE"] == "res://Main.tscn"


def test_verify_no_errors_false_when_logs_have_script_error(tmp_path, monkeypatch) -> None:
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd, 0, stdout="PLAYSMITH_ASSERT player_exists=true\n", stderr="SCRIPT ERROR: boom\n"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    a = _adapter(tmp_path)
    a.create_project("G", main_scene="res://Main.tscn")
    vr = a.verify(checks=["player_exists", "no_errors"])
    assert vr.assertions["no_errors"] is False
    assert not vr.ok


def test_export_desktop_target_writes_matching_preset(tmp_path, monkeypatch) -> None:
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="exported")

    monkeypatch.setattr(subprocess, "run", fake_run)
    a = _adapter(tmp_path)
    a.create_project("G", main_scene="res://Main.tscn")
    a.export(ExportTarget.WINDOWS, str(tmp_path / "build" / "game.exe"))
    presets = (a.project_dir / "export_presets.cfg").read_text()
    assert 'name="Windows Desktop"' in presets
    assert "Windows Desktop" in captured["cmd"]


def test_export_appends_second_preset_without_clobbering(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        subprocess, "run", lambda cmd, **k: subprocess.CompletedProcess(cmd, 0, stdout="ok")
    )
    a = _adapter(tmp_path)
    a.create_project("G", main_scene="res://Main.tscn")
    a.export(ExportTarget.WEB, str(tmp_path / "b" / "index.html"))
    a.export(ExportTarget.LINUX, str(tmp_path / "b" / "game.x86_64"))
    presets = (a.project_dir / "export_presets.cfg").read_text()
    assert 'name="Web"' in presets and 'name="Linux/X11"' in presets
    assert "[preset.0]" in presets and "[preset.1]" in presets


def test_export_android_writes_android_preset(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        subprocess, "run", lambda cmd, **k: subprocess.CompletedProcess(cmd, 0, stdout="ok")
    )
    a = _adapter(tmp_path)
    a.create_project("G", main_scene="res://Main.tscn")
    a.export(ExportTarget.ANDROID, str(tmp_path / "b" / "game.aab"))
    assert 'name="Android"' in (a.project_dir / "export_presets.cfg").read_text()


def test_screenshot_injects_harness_and_passes_env(tmp_path, monkeypatch) -> None:
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    a = _adapter(tmp_path)
    a.create_project("G", main_scene="res://Main.tscn")
    out = tmp_path / "shot.png"
    a.screenshot(str(out))
    assert (a.project_dir / templates.SCREENSHOT_SCRIPT).exists()
    assert (a.project_dir / templates.SCREENSHOT_SCENE).exists()
    assert captured["env"]["PLAYSMITH_SCREENSHOT"] == str(out.resolve())
    assert captured["env"]["PLAYSMITH_TARGET_SCENE"] == "res://Main.tscn"
