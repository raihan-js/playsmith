"""Tests for art generation + the asset endpoints. No network, no Unreal."""

from __future__ import annotations

import base64

import pytest

from playsmith.config import Config, LLMConfig
from playsmith.llm import imagegen

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from playsmith.web.server import app  # noqa: E402


class _Resp:
    def __init__(self, status: int = 200, payload=None, content: bytes = b"") -> None:
        self.status_code = status
        self._payload = payload
        self.content = content
        self.text = "error-body"

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class _Client:
    def __init__(self, post: _Resp | None = None, get: _Resp | None = None) -> None:
        self._post, self._get = post, get

    def post(self, url, json=None, headers=None, timeout=None):  # noqa: A002
        return self._post

    def get(self, url, timeout=None):
        return self._get


_PROVIDER = imagegen.ImageProvider("https://api.openai.com/v1", "sk-x", "gpt-image-1")


# -- provider resolution -----------------------------------------------------------
def test_resolve_prefers_openai_env_key(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    p = imagegen.resolve_image_provider(Config())
    assert p and p.base_url == "https://api.openai.com/v1" and p.api_key == "sk-env"


def test_resolve_none_when_unconfigured(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert imagegen.resolve_image_provider(Config()) is None


def test_resolve_uses_openai_compatible_llm(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    cfg = Config(llm=LLMConfig(provider="openai", base_url="https://api.openai.com/v1",
                               api_key="sk-cfg", kind="openai"))
    p = imagegen.resolve_image_provider(cfg)
    assert p and p.api_key == "sk-cfg"


# -- generation --------------------------------------------------------------------
def test_generate_decodes_b64() -> None:
    payload = {"data": [{"b64_json": base64.b64encode(b"PNGDATA").decode()}]}
    client = _Client(post=_Resp(payload=payload))
    assert imagegen.generate_image(_PROVIDER, "a lava texture", client=client) == b"PNGDATA"


def test_generate_fetches_url() -> None:
    client = _Client(post=_Resp(payload={"data": [{"url": "http://img/x.png"}]}),
                     get=_Resp(content=b"BYTES"))
    assert imagegen.generate_image(_PROVIDER, "art", client=client) == b"BYTES"


def test_generate_raises_on_http_error() -> None:
    with pytest.raises(imagegen.ImageGenError, match="HTTP 401"):
        imagegen.generate_image(_PROVIDER, "art", client=_Client(post=_Resp(status=401)))


def test_generate_requires_prompt() -> None:
    with pytest.raises(imagegen.ImageGenError):
        imagegen.generate_image(_PROVIDER, "   ", client=_Client(post=_Resp(payload={})))


# -- endpoints ---------------------------------------------------------------------
def _workspace_with_project(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    (ws / "my-game").mkdir(parents=True)
    (ws / "my-game" / "Game.uproject").write_text("{}")
    cfg = tmp_path / "playsmith.yaml"
    cfg.write_text(f"workspace_dir: {ws}\nllm:\n  provider: ollama\n  model: x\n")
    monkeypatch.setenv("PLAYSMITH_CONFIG", str(cfg))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return ws


def test_asset_disabled_without_provider(tmp_path, monkeypatch) -> None:
    # load_config() auto-loads the repo .env, so disable explicitly via the resolver.
    _workspace_with_project(tmp_path, monkeypatch)
    monkeypatch.setattr(imagegen, "resolve_image_provider", lambda cfg=None: None)
    resp = TestClient(app).post("/api/projects/my-game/asset", json={"prompt": "lava"})
    assert resp.status_code == 503 and "OPENAI_API_KEY" in resp.json()["error"]


def test_asset_generate_save_serve_and_list(tmp_path, monkeypatch) -> None:
    ws = _workspace_with_project(tmp_path, monkeypatch)
    monkeypatch.setattr(imagegen, "resolve_image_provider", lambda cfg=None: _PROVIDER)
    monkeypatch.setattr(imagegen, "generate_image", lambda *a, **k: b"\x89PNG\r\n\x1a\nDATA")
    client = TestClient(app)

    gen = client.post("/api/projects/my-game/asset", json={"prompt": "Lava Rocks"})
    assert gen.status_code == 200
    body = gen.json()
    assert body["ok"] and body["name"].endswith(".png") and "lava-rocks" in body["name"]
    saved = ws / "my-game" / "Saved" / "Playsmith" / "art" / body["name"]
    assert saved.exists() and saved.read_bytes().startswith(b"\x89PNG")

    served = client.get(body["file"])
    assert served.status_code == 200 and served.headers["content-type"] == "image/png"

    listing = client.get("/api/projects/my-game/assets").json()
    assert listing["enabled"] is True
    assert [a["name"] for a in listing["assets"]] == [body["name"]]
    assert listing["assets"][0]["prompt"] == "Lava Rocks"


def test_asset_requires_prompt_and_real_project(tmp_path, monkeypatch) -> None:
    _workspace_with_project(tmp_path, monkeypatch)
    monkeypatch.setattr(imagegen, "resolve_image_provider", lambda cfg=None: _PROVIDER)
    client = TestClient(app)
    assert client.post("/api/projects/my-game/asset", json={"prompt": ""}).status_code == 400
    assert client.post("/api/projects/nope/asset", json={"prompt": "x"}).status_code == 404


def test_asset_file_path_traversal_safe(tmp_path, monkeypatch) -> None:
    _workspace_with_project(tmp_path, monkeypatch)
    resp = TestClient(app).get("/api/projects/my-game/asset-file/..%2f..%2fmanifest.json")
    assert resp.status_code == 404
