"""Smoke tests for the web UI (skipped if the `web` extra isn't installed)."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from playsmith.web.server import app  # noqa: E402


def _client() -> TestClient:
    return TestClient(app)


def test_index_is_served() -> None:
    resp = _client().get("/")
    assert resp.status_code == 200
    assert "Playsmith" in resp.text


def test_config_endpoint() -> None:
    cfg = _client().get("/api/config").json()
    assert "model" in cfg and "workspace" in cfg


def test_skills_endpoint_lists_builtins() -> None:
    skills = _client().get("/api/skills").json()
    assert any(s["name"] == "2d-platformer" for s in skills)


def test_projects_endpoint_returns_list() -> None:
    assert isinstance(_client().get("/api/projects").json(), list)


def test_unknown_project_files_404() -> None:
    assert _client().get("/api/projects/does-not-exist-xyz/files").status_code == 404


def test_index_is_wired_live_not_mock() -> None:
    # The shipped UI must talk to the real backend, not the design's MOCK layer.
    html = _client().get("/").text
    assert "const MOCK" not in html
    assert "/ws/pull" in html and "/api/models" in html and "gameFrame" in html


def test_skills_include_genre() -> None:
    skills = _client().get("/api/skills").json()
    plat = next(s for s in skills if s["name"] == "2d-platformer")
    assert plat["genre"] == "Platformer"


def test_models_endpoint_shape(monkeypatch) -> None:
    # Stub discovery so the test never touches the network.
    from playsmith.web import server

    monkeypatch.setattr(
        server.model_catalog,
        "catalog",
        lambda cfg: {"active": {"provider": "openai", "model": "gpt-4o"},
                     "providers": [{"id": "openai"}, {"id": "ollama"}]},
    )
    data = _client().get("/api/models").json()
    assert data["active"]["model"] == "gpt-4o"
    assert {p["id"] for p in data["providers"]} == {"openai", "ollama"}


def test_set_config_requires_provider_and_model() -> None:
    assert _client().post("/api/config", json={"provider": "openai"}).status_code == 400


def test_export_unknown_project_404() -> None:
    r = _client().post("/api/projects/nope-xyz/export", json={"target": "web"})
    assert r.status_code == 404


def test_download_unknown_project_404() -> None:
    assert _client().get("/api/projects/nope-xyz/download/linux").status_code == 404
