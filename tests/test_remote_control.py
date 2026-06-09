"""Tests for the editor-in-the-loop (Remote Control) authoring path. No editor, no network."""

from __future__ import annotations

import types

import pytest

from playsmith.engines.base import EngineError, RunResult
from playsmith.engines.unreal import render
from playsmith.engines.unreal.adapter import RemoteControlClient, UnrealAdapter


class _FakeResp:
    def __init__(self, status: int = 200, payload=None) -> None:
        self.status_code = status
        self._payload = payload or {}
        self.text = "err"

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, resp: _FakeResp | None = None) -> None:
        self.calls: list[dict] = []
        self._resp = resp or _FakeResp()

    def request(self, method, url, timeout=None, json=None):  # noqa: A002
        self.calls.append({"method": method, "url": url, "json": json, "timeout": timeout})
        return self._resp


def test_execute_python_targets_the_python_script_library() -> None:
    fc = _FakeClient(_FakeResp(payload={"ReturnValue": True}))
    RemoteControlClient(client=fc).execute_python("import unreal", timeout=120.0)
    call = fc.calls[-1]
    assert call["method"] == "PUT" and "/remote/object/call" in call["url"]
    body = call["json"]
    assert "PythonScriptLibrary" in body["objectPath"]
    assert body["functionName"] == "ExecutePythonCommand"
    assert body["parameters"]["PythonCommand"] == "import unreal"
    assert call["timeout"] == 120.0


def test_available_reflects_status() -> None:
    assert RemoteControlClient(client=_FakeClient(_FakeResp(200))).available() is True
    assert RemoteControlClient(client=_FakeClient(_FakeResp(503))).available() is False


def _adapter(tmp_path) -> UnrealAdapter:
    return UnrealAdapter(tmp_path, editor_cmd="UnrealEditor-Cmd")


def test_author_uses_live_editor_when_available(tmp_path, monkeypatch) -> None:
    a = _adapter(tmp_path)
    a.remote = types.SimpleNamespace(
        available=lambda: True, execute_python=lambda cmd, timeout=None: {"ReturnValue": True}
    )

    def _no_commandlet(*args, **kwargs):
        raise AssertionError("should not fall back to the headless commandlet")

    monkeypatch.setattr(a, "_run_python", _no_commandlet)
    res = a._author("print('x')", out_file=tmp_path / "Saved" / "out.txt")
    assert res.returncode == 0 and res.command == ["remote", "execute_python"]
    assert (tmp_path / "Saved" / "playsmith_live.py").read_text() == "print('x')"


def test_author_falls_back_to_commandlet_without_editor(tmp_path, monkeypatch) -> None:
    a = _adapter(tmp_path)
    a.remote = types.SimpleNamespace(available=lambda: False)
    monkeypatch.setattr(
        a, "_run_python",
        lambda script, *, timeout_s, out_file: RunResult(command=["cmdlet"], returncode=0),
    )
    assert a._author("x", out_file=tmp_path / "o.txt").command == ["cmdlet"]


def test_run_python_live_reports_remote_errors(tmp_path) -> None:
    def boom(cmd, timeout=None):
        raise EngineError("no editor")

    a = _adapter(tmp_path)
    a.remote = types.SimpleNamespace(available=lambda: True, execute_python=boom)
    res = a._run_python_live("x", out_file=tmp_path / "Saved" / "o.txt")
    assert res.returncode == 1 and "no editor" in (res.stderr or "")


def test_scene_capture_script_renders_to_png() -> None:
    s = render.scene_capture_script("/Game/X/Lvl", "/tmp/shot.png", 1280, 720)
    assert "SceneCapture2D" in s and "export_render_target" in s  # works in a live render context
    assert "/Game/X/Lvl" in s and "/tmp/shot.png" in s
    assert "PLAYSMITH_ASSERT scene_capture" in s


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__])
