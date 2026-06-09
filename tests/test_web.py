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
    projects = _list_projects(tmp_path)
    assert [p["name"] for p in projects] == ["game-a"]
    assert projects[0]["has_preview"] is True
    assert projects[0]["genre"] == "third-person"  # default when no manifest


def test_list_projects_reads_manifest(tmp_path) -> None:
    g = tmp_path / "lava"
    g.mkdir()
    (g / "G.uproject").write_text("{}")
    (g / ".playsmith").mkdir()
    (g / ".playsmith" / "manifest.json").write_text(
        json.dumps({"genre": "first-person", "objective": "shoot the targets", "playable": True})
    )
    p = _list_projects(tmp_path)[0]
    assert p["genre"] == "first-person"
    assert p["prompt"] == "shoot the targets"


def test_config_and_skills_endpoints() -> None:
    client = TestClient(app)
    cfg = client.get("/api/config").json()
    assert "model" in cfg and cfg["where"] in ("local", "cloud")
    skills = {s["name"] for s in client.get("/api/skills").json()["skills"]}
    assert skills == {"first-person", "third-person", "top-down"}


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
