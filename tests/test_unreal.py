"""Tests for the experimental Unreal adapter (Remote Control + subprocess mocked)."""

from __future__ import annotations

import json
import subprocess

import httpx
import pytest
from typer.testing import CliRunner

from playsmith.cli.main import app
from playsmith.engines.base import EngineAdapter, EngineError, EngineNotFoundError, RunResult
from playsmith.engines.unreal import RemoteControlClient, UnrealAdapter, royalty_estimate


# -- royalty calculator (pure) ---------------------------------------------------
def test_royalty_zero_below_threshold() -> None:
    assert royalty_estimate(500_000)["royalty_owed"] == 0.0


def test_royalty_five_percent_above_threshold() -> None:
    est = royalty_estimate(2_000_000)
    assert est["royaltyable_revenue"] == 1_000_000
    assert est["royalty_owed"] == 50_000.0  # 5% of the $1M over the threshold


def test_royalty_egs_rate_and_exempt() -> None:
    est = royalty_estimate(3_000_000, via_egs=True, egs_exempt_revenue=1_000_000)
    # (3M - 1M exempt) - 1M threshold = 1M royaltyable at 3.5%.
    assert est["royaltyable_revenue"] == 1_000_000
    assert est["royalty_owed"] == 35_000.0
    assert est["via_egs"]


# -- Remote Control client -------------------------------------------------------
def test_remote_available_true() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    assert RemoteControlClient(client=client).available()


def test_remote_call_builds_put_request() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ReturnValue": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = RemoteControlClient(client=client).call("/Game/Obj", "DoThing", {"x": 1})
    assert out == {"ReturnValue": True}
    assert captured["method"] == "PUT"
    assert captured["path"] == "/remote/object/call"
    assert captured["body"]["functionName"] == "DoThing"


# -- adapter ---------------------------------------------------------------------
def test_unreal_adapter_satisfies_engine_protocol(tmp_path) -> None:
    adapter = UnrealAdapter(tmp_path / "proj")
    assert isinstance(adapter, EngineAdapter)  # satisfies the EngineAdapter interface


def test_create_project_writes_blueprint_uproject_and_boot_config(tmp_path) -> None:
    adapter = UnrealAdapter(tmp_path / "proj")
    adapter.create_project("MyGame", main_scene="/Game/Maps/Main")
    files = list((tmp_path / "proj").glob("*.uproject"))
    assert files, "a .uproject should be written"
    data = json.loads(files[0].read_text())
    assert data["Description"] == "MyGame"
    assert data["Modules"] == []  # Blueprint-only: nothing to compile
    assert any(p["Name"] == "PythonScriptPlugin" and p["Enabled"] for p in data["Plugins"])
    ini = (tmp_path / "proj" / "Config" / "DefaultEngine.ini").read_text()
    assert "GameDefaultMap=/Game/Maps/Main" in ini


def test_scaffold_runs_the_pythonscript_commandlet(tmp_path, monkeypatch) -> None:
    adapter = UnrealAdapter(tmp_path / "proj")
    adapter.create_project("G")
    captured: dict = {}

    def fake_invoke(args, *, timeout_s, env=None):
        captured["args"] = args
        return RunResult(command=["ue"], returncode=0)

    monkeypatch.setattr(adapter, "_invoke", fake_invoke)
    adapter.scaffold()
    assert any("-run=pythonscript" in str(a) for a in captured["args"])
    written = (tmp_path / "proj" / "Saved" / "playsmith_run.py").read_text()
    assert "spawn_actor_from_class" in written and "PlayerStart" in written


def test_verify_parses_file_based_assertions(tmp_path, monkeypatch) -> None:
    adapter = UnrealAdapter(tmp_path / "proj")
    adapter.create_project("G")

    def fake_run_python(script_text, *, timeout_s, out_file=None):
        if out_file is not None:  # emulate the UE Python harness writing its result file
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(
                "PLAYSMITH_ASSERT level_loads=true\n"
                "PLAYSMITH_ASSERT player_start_exists=true\n"
                "PLAYSMITH_ASSERT floor_exists=true\n"
                "PLAYSMITH_ASSERT player_exists=true\n"
            )
        return RunResult(command=["ue"], returncode=0, stdout="ok")

    monkeypatch.setattr(adapter, "_run_python", fake_run_python)
    result = adapter.verify(
        checks=["level_loads", "player_start_exists", "floor_exists", "player_exists"]
    )
    assert result.assertions["player_exists"] is True
    assert result.ok


def test_write_scene_refused_binary(tmp_path) -> None:
    from playsmith.engines.base import SceneSpec

    adapter = UnrealAdapter(tmp_path / "proj")
    with pytest.raises(EngineError, match="binary"):
        adapter.write_scene(SceneSpec("Main.umap", "x"))


def test_run_builds_command_and_handles_missing_binary(tmp_path, monkeypatch) -> None:
    adapter = UnrealAdapter(tmp_path / "proj")
    adapter.create_project("G")

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="LogInit: Display: ok")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = adapter.run(headless=True)
    assert result.returncode == 0
    assert "-game" in captured["cmd"] and "-nullrhi" in captured["cmd"]

    def boom(cmd, **kwargs):
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(subprocess, "run", boom)
    with pytest.raises(EngineNotFoundError):
        adapter.run()


# -- CLI -------------------------------------------------------------------------
def test_cli_unreal_royalty() -> None:
    result = CliRunner().invoke(app, ["unreal", "royalty", "2000000"])
    assert result.exit_code == 0
    assert "50,000" in result.output  # 5% of $1M over the threshold
