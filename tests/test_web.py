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
