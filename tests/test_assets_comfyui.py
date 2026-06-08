"""Tests for the ComfyUI asset pipeline and graceful placeholder fallback (HTTP mocked)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from playsmith.agent import AutoApprover, ToolContext, execute
from playsmith.assets import ComfyUIClient, get_asset_generator
from playsmith.assets.base import AssetGenerator
from playsmith.config import AssetsConfig, Config
from playsmith.llm import ToolCall
from tests.conftest import FakeAdapter


def _client(handler) -> ComfyUIClient:
    return ComfyUIClient(
        "http://localhost:8188",
        poll_interval=0.01,
        timeout=1.0,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_available_true_when_system_stats_ok() -> None:
    c = _client(lambda r: httpx.Response(200, json={"system": {}}))
    assert c.available()


def test_available_false_when_unreachable() -> None:
    def handler(_req):
        raise httpx.ConnectError("refused")

    assert not _client(handler).available()


def test_image_runs_workflow_and_writes_file(tmp_path) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path == "/prompt":
            captured["workflow"] = json.loads(request.content)["prompt"]
            return httpx.Response(200, json={"prompt_id": "p1"})
        if path == "/history/p1":
            return httpx.Response(
                200,
                json={
                    "p1": {"outputs": {"9": {"images": [{"filename": "a.png", "type": "output"}]}}}
                },
            )
        if path == "/view":
            return httpx.Response(200, content=b"PNGDATA")
        return httpx.Response(404)

    out = tmp_path / "assets" / "cat.png"
    _client(handler).image("a cat", "sprite", str(out))
    assert out.read_bytes() == b"PNGDATA"
    # The positive prompt reached ComfyUI, with the sprite style hint appended.
    text = captured["workflow"]["6"]["inputs"]["text"]
    assert "a cat" in text and "pixel art" in text


def test_mesh_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        ComfyUIClient().mesh("a tree", "/tmp/x.glb")


def test_get_asset_generator_respects_enabled_flag() -> None:
    assert get_asset_generator(Config(assets=AssetsConfig(enabled=False))) is None
    gen = get_asset_generator(Config(assets=AssetsConfig(enabled=True)))
    assert isinstance(gen, AssetGenerator)


# -- the _generate_asset tool's graceful degradation -----------------------------
class _FakeGen:
    def available(self) -> bool:
        return True

    def image(self, prompt: str, kind: str, out_path: str) -> None:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"IMG")

    def mesh(self, prompt_or_image: str, out_path: str) -> None:  # pragma: no cover
        raise NotImplementedError


def _ctx(tmp_path, gen=None) -> ToolContext:
    return ToolContext(
        adapter=FakeAdapter(tmp_path / "game"), approver=AutoApprover(), asset_generator=gen
    )


def test_generate_asset_tool_falls_back_to_placeholder(tmp_path) -> None:
    ctx = _ctx(tmp_path, gen=None)
    msg = execute(ToolCall(id="1", name="generate_asset", arguments={"prompt": "a cat"}), ctx)
    assert "placeholder" in msg.lower()


def test_generate_asset_tool_uses_generator_when_available(tmp_path) -> None:
    ctx = _ctx(tmp_path, gen=_FakeGen())
    msg = execute(
        ToolCall(
            id="1", name="generate_asset", arguments={"prompt": "a happy cat", "kind": "sprite"}
        ),
        ctx,
    )
    assert "res://assets/" in msg
    assert (ctx.workspace / "assets" / "a_happy_cat.png").read_bytes() == b"IMG"
