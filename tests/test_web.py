"""Tests for the optional web UI (skipped if the `web` extra isn't installed). No Unreal needed."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from playsmith.web.server import _list_projects, _slug, app  # noqa: E402


def test_slug_normalizes() -> None:
    assert _slug("A Cool Game!") == "a-cool-game"
    assert _slug("") == "unreal-game"


def test_list_projects_finds_only_uproject_dirs(tmp_path) -> None:
    good = tmp_path / "game-a"
    (good / "x").mkdir(parents=True)
    (good / "Game.uproject").write_text("{}")
    (good / "preview.png").write_bytes(b"\x89PNG")
    (tmp_path / "not-a-project").mkdir()  # no .uproject -> excluded
    assert _list_projects(tmp_path) == [{"name": "game-a", "has_preview": True}]


def test_index_and_genres_served() -> None:
    client = TestClient(app)
    home = client.get("/")
    assert home.status_code == 200 and "Playsmith" in home.text
    assert "third-person" in client.get("/api/genres").json()["genres"]


def test_preview_missing_is_404() -> None:
    assert TestClient(app).get("/preview/definitely-not-a-real-project").status_code == 404


def test_ws_reports_errors_without_touching_unreal() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"action": "render", "name": "nope", "genre": "third-person"}))
        assert json.loads(ws.receive_text())["type"] == "error"
        ws.send_text(json.dumps({"action": "build", "genre": "no-such-genre"}))
        assert json.loads(ws.receive_text())["type"] == "error"
        ws.send_text(json.dumps({"action": "play", "name": "nope", "genre": "third-person"}))
        assert json.loads(ws.receive_text())["type"] == "error"
        ws.send_text(json.dumps({"action": "bogus"}))
        assert json.loads(ws.receive_text())["type"] == "error"
