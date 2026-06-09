"""Tests for the model catalog + Settings endpoints. No network, no Unreal."""

from __future__ import annotations

import json

import pytest

from playsmith.config import Config, LLMConfig
from playsmith.llm import catalog

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from playsmith.web.server import app  # noqa: E402


def test_config_patch_resolves_known_provider() -> None:
    patch = catalog.config_patch_for("anthropic", "claude-opus-4-8", api_key="sk-test")
    assert patch == {
        "llm": {
            "provider": "anthropic",
            "base_url": "https://api.anthropic.com/v1",
            "model": "claude-opus-4-8",
            "kind": "anthropic",
            "api_key": "sk-test",
        }
    }


def test_config_patch_pulls_key_from_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    patch = catalog.config_patch_for("openai", "gpt-4o")
    assert patch["llm"]["api_key"] == "sk-env" and patch["llm"]["kind"] == "openai"


def test_config_patch_local_provider_omits_empty_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    patch = catalog.config_patch_for("ollama", "llama3.2")
    assert "api_key" not in patch["llm"] and patch["llm"]["base_url"].endswith(":11434/v1")


def test_config_patch_unknown_provider_needs_base_url() -> None:
    with pytest.raises(ValueError, match="base_url"):
        catalog.config_patch_for("mystery", "some-model")
    patch = catalog.config_patch_for("mystery", "m", base_url="http://x/v1")
    assert patch["llm"] == {"provider": "mystery", "base_url": "http://x/v1",
                            "model": "m", "kind": "openai"}


def test_config_patch_requires_provider_and_model() -> None:
    with pytest.raises(ValueError):
        catalog.config_patch_for("", "model")
    with pytest.raises(ValueError):
        catalog.config_patch_for("ollama", "")


def test_catalog_marks_current_and_readiness(monkeypatch) -> None:
    monkeypatch.setattr(catalog, "discover_ollama", lambda *a, **k: [])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-yes")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    cfg = Config(llm=LLMConfig(provider="anthropic", model="claude-opus-4-8",
                               base_url="https://api.anthropic.com/v1", kind="anthropic"))
    data = catalog.catalog(cfg)
    by_id = {p["id"]: p for p in data["providers"]}
    assert data["current"]["provider"] == "anthropic" and data["current"]["where"] == "cloud"
    assert by_id["anthropic"]["current"] is True and by_id["anthropic"]["ready"] is True
    assert by_id["openrouter"]["ready"] is False  # no key in env
    assert by_id["ollama"]["ready"] is True  # local needs no key
    opus = next(m for m in by_id["anthropic"]["models"] if m["id"] == "claude-opus-4-8")
    assert opus["current"] is True and opus["vision"] is True


def test_catalog_uses_discovered_ollama_models(monkeypatch) -> None:
    monkeypatch.setattr(
        catalog, "discover_ollama", lambda *a, **k: [catalog.ModelInfo("mistral:7b", "mistral:7b")]
    )
    data = catalog.catalog(Config())
    ollama = next(p for p in data["providers"] if p["id"] == "ollama")
    assert [m["id"] for m in ollama["models"]] == ["mistral:7b"]


def test_discover_ollama_swallows_errors() -> None:
    class _Boom:
        def get(self, *a, **k):
            raise __import__("httpx").ConnectError("refused")

    assert catalog.discover_ollama("http://localhost:11434/v1", client=_Boom()) == []


# -- endpoints ---------------------------------------------------------------------
def test_api_models_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(catalog, "discover_ollama", lambda *a, **k: [])
    data = TestClient(app).get("/api/models").json()
    ids = {p["id"] for p in data["providers"]}
    assert {"anthropic", "openai", "ollama"} <= ids
    assert "current" in data


def test_post_config_persists_pick(monkeypatch, tmp_path) -> None:
    cfg_file = tmp_path / "playsmith.yaml"
    cfg_file.write_text("llm:\n  provider: ollama\n  model: qwen2.5-coder:7b\n"
                        "  base_url: http://localhost:11434/v1\n")
    monkeypatch.setenv("PLAYSMITH_CONFIG", str(cfg_file))
    client = TestClient(app)
    resp = client.post("/api/config", json={"provider": "anthropic", "model": "claude-opus-4-8",
                                            "api_key": "sk-abc"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] and body["provider"] == "anthropic" and body["where"] == "cloud"
    override = tmp_path / "playsmith.runtime.yaml"
    assert override.exists() and "claude-opus-4-8" in override.read_text()


def test_post_config_rejects_incomplete(monkeypatch, tmp_path) -> None:
    cfg_file = tmp_path / "playsmith.yaml"
    cfg_file.write_text("llm:\n  provider: ollama\n  model: x\n")
    monkeypatch.setenv("PLAYSMITH_CONFIG", str(cfg_file))
    bad = TestClient(app).post("/api/config", json={"provider": "anthropic"})
    assert bad.status_code == 400 and "error" in bad.json()


def test_post_config_ignores_malformed_body(monkeypatch, tmp_path) -> None:
    cfg_file = tmp_path / "playsmith.yaml"
    cfg_file.write_text("llm:\n  provider: ollama\n  model: x\n")
    monkeypatch.setenv("PLAYSMITH_CONFIG", str(cfg_file))
    resp = TestClient(app).post("/api/config", content=b"not json",
                                headers={"content-type": "application/json"})
    assert resp.status_code == 400


if __name__ == "__main__":  # pragma: no cover
    print(json.dumps(catalog.catalog(Config())["current"]))
