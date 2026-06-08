"""Tests for the OpenAI image-generation backend (HTTP mocked)."""

from __future__ import annotations

import base64
import json

import httpx

from playsmith.assets import OpenAIImageClient, get_asset_generator
from playsmith.config import AssetsConfig, Config, LLMConfig


def _client(handler) -> OpenAIImageClient:
    return OpenAIImageClient("sk-test", client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_available_requires_key() -> None:
    assert OpenAIImageClient("sk-x").available()
    assert not OpenAIImageClient("").available()


def test_image_decodes_b64_and_writes_png(tmp_path) -> None:
    png = b"\x89PNG\r\n\x1a\nSPRITEDATA"
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(png).decode()}]})

    out = tmp_path / "assets" / "hero.png"
    _client(handler).image("a ninja frog", "sprite", str(out))
    assert out.read_bytes() == png
    assert captured["url"].endswith("/images/generations")
    assert captured["auth"] == "Bearer sk-test"
    assert "ninja frog" in captured["body"]["prompt"]
    assert captured["body"]["background"] == "transparent"  # gpt-image-1 transparent sprite


def test_get_asset_generator_openai_falls_back_to_llm_key() -> None:
    cfg = Config(
        llm=LLMConfig(provider="openai", api_key="sk-llm"),
        assets=AssetsConfig(enabled=True, image_backend="openai"),
    )
    gen = get_asset_generator(cfg)
    assert isinstance(gen, OpenAIImageClient)
    assert gen.api_key == "sk-llm"


def test_get_asset_generator_openai_none_without_any_key() -> None:
    cfg = Config(assets=AssetsConfig(enabled=True, image_backend="openai"))  # llm default = ollama
    assert get_asset_generator(cfg) is None
