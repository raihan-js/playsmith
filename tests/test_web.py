"""Tests for the optional web UI (skipped if the `web` extra isn't installed). No Unreal needed."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from playsmith.web.server import _list_projects, _slug, app  # noqa: E402


def _tmp_workspace(tmp_path, monkeypatch):
    """Point the app at a throwaway config whose workspace is under tmp_path."""
    ws = tmp_path / "ws"
    ws.mkdir()
    cfg = tmp_path / "playsmith.yaml"
    cfg.write_text(f"workspace_dir: {ws}\nllm:\n  provider: ollama\n  model: x\n")
    monkeypatch.setenv("PLAYSMITH_CONFIG", str(cfg))
    return ws


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


def test_list_projects_includes_title(tmp_path) -> None:
    g = tmp_path / "neon-drift"
    g.mkdir()
    (g / "G.uproject").write_text("{}")
    assert _list_projects(tmp_path)[0]["title"] == "Neon Drift"  # prettified fallback
    (g / ".playsmith").mkdir()
    (g / ".playsmith" / "manifest.json").write_text(json.dumps({"title": "Neon Drift GP"}))
    assert _list_projects(tmp_path)[0]["title"] == "Neon Drift GP"  # manifest wins


def test_delete_project_is_workspace_scoped(tmp_path, monkeypatch) -> None:
    ws = _tmp_workspace(tmp_path, monkeypatch)
    proj = ws / "my-game"
    proj.mkdir()
    (proj / "Game.uproject").write_text("{}")
    plain = ws / "plain"  # a dir with no .uproject must not be deletable
    plain.mkdir()
    client = TestClient(app)
    assert client.delete("/api/projects/nope").status_code == 404
    assert client.delete("/api/projects/plain").status_code == 404 and plain.exists()
    ok = client.delete("/api/projects/my-game")
    assert ok.status_code == 200 and ok.json()["ok"] is True
    assert not proj.exists()


def test_delete_handles_long_cli_names(tmp_path, monkeypatch) -> None:
    """Regression: CLI-made projects have full untruncated folder names; delete must still work."""
    ws = _tmp_workspace(tmp_path, monkeypatch)
    longname = "make-a-survival-simulation-where-a-player-is-stranded-on-an-island-" + "x" * 40
    proj = ws / longname
    proj.mkdir()
    (proj / "G.uproject").write_text("{}")
    assert _slug(longname) != longname  # the bug: re-slugging would truncate and never match
    resp = TestClient(app).delete("/api/projects/" + longname)
    assert resp.status_code == 200 and not proj.exists()


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


def test_ws_build_streams_clone_verify_critic_done(tmp_path, monkeypatch) -> None:
    """Drive a full build over the websocket with a faked adapter — exercises the refine bridge."""
    from types import SimpleNamespace

    from playsmith.engines.unreal import director as drct
    from playsmith.engines.unreal import template_clone
    from playsmith.web import server as srv

    ws = _tmp_workspace(tmp_path, monkeypatch)
    tspec = template_clone.TEMPLATES["third-person"]

    class FakeAdapter:
        def __init__(self, *a, **k) -> None:
            pass

        def create_from_template(self, genre, project_name):
            return tspec

        def verify_template(self, spec):
            return SimpleNamespace(ok=True, assertions={"level_loads": True})

        def dress_from_spec(self, spec, map_path):
            return SimpleNamespace(
                ok=True,
                assertions={"level_loads": True, "objects_placed": True, "goal_exists": True},
            )

        def customize_character(self, spec, tspec):
            return SimpleNamespace(ok=True, assertions={"character_customized": True})

        def live_available(self):
            return False  # no live editor in tests -> builtin prototype pack

        def discover_assets(self, *a, **k):
            return {}

    monkeypatch.setattr(srv, "UnrealAdapter", FakeAdapter)
    monkeypatch.setattr(srv.LLMGateway, "from_config", staticmethod(lambda cfg, **k: object()))
    rich = drct._augment(drct.default_dressing(), size="large")  # passes the critic on pass 1
    monkeypatch.setattr(drct, "plan_dressing", lambda *a, **k: rich)

    with TestClient(app).websocket_connect("/ws") as sock:
        sock.send_text(json.dumps(
            {"action": "build", "prompt": "a temple run", "genre": "third-person", "iterations": 1}
        ))
        seen, done = [], None
        for _ in range(40):
            msg = json.loads(sock.receive_text())
            seen.append(msg["type"])
            if msg["type"] == "done":
                done = msg
                break
    assert "critic" in seen and done is not None
    assert done["title"] and done.get("quality") is not None
    manifest = json.loads((ws / _slug("a temple run") / ".playsmith" / "manifest.json").read_text())
    assert manifest["title"] == done["title"] and "quality" in manifest


def test_ws_improve_streams_and_saves(tmp_path, monkeypatch) -> None:
    """The 'keep improving' agent runs the refine loop on an existing project and saves quality."""
    from types import SimpleNamespace

    from playsmith.engines.unreal import director as drct
    from playsmith.web import server as srv

    ws = _tmp_workspace(tmp_path, monkeypatch)
    proj = ws / "mygame"
    (proj / ".playsmith").mkdir(parents=True)
    (proj / "G.uproject").write_text("{}")
    (proj / ".playsmith" / "manifest.json").write_text(
        json.dumps({"genre": "third-person", "objective": "reach the goal"})
    )

    class FakeAdapter:
        def __init__(self, *a, **k) -> None:
            self.project_dir = proj

        def dress_from_spec(self, spec, map_path):
            return SimpleNamespace(
                ok=True,
                assertions={"level_loads": True, "objects_placed": True, "goal_exists": True},
            )

        def customize_character(self, spec, tspec):
            return SimpleNamespace(ok=True, assertions={"character_customized": True})

        def live_available(self):
            return False  # no live editor in tests -> builtin prototype pack

        def discover_assets(self, *a, **k):
            return {}

    monkeypatch.setattr(srv, "UnrealAdapter", FakeAdapter)
    monkeypatch.setattr(srv.LLMGateway, "from_config", staticmethod(lambda cfg, **k: object()))
    monkeypatch.setattr(drct, "plan_dressing",
                        lambda *a, **k: drct._augment(drct.default_dressing(), size="large"))

    with TestClient(app).websocket_connect("/ws") as sock:
        sock.send_text(json.dumps({"action": "improve", "name": "mygame", "rounds": 2}))
        seen, done = [], None
        for _ in range(50):
            msg = json.loads(sock.receive_text())
            seen.append(msg["type"])
            if msg["type"] == "done":
                done = msg
                break
    assert "critic" in seen and done is not None and done["title"]
    manifest = json.loads((proj / ".playsmith" / "manifest.json").read_text())
    assert "quality" in manifest


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
