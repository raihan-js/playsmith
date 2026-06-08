"""Tests for the 3D mesh pipeline and primitive fallback (HTTP mocked, no Blender)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from playsmith.agent import AutoApprover, ToolContext, execute
from playsmith.assets import MeshClient, MeshGenerator, get_mesh_generator
from playsmith.config import AssetsConfig, Config
from playsmith.llm import ToolCall
from tests.conftest import FakeAdapter


def _client(handler) -> MeshClient:
    return MeshClient(
        "http://localhost:8080",
        timeout=1.0,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_available_false_without_url() -> None:
    assert not MeshClient("").available()


def test_available_true_when_health_ok() -> None:
    assert _client(lambda r: httpx.Response(200, json={"ok": True})).available()


def test_mesh_octet_stream_written(tmp_path) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/generate":
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                200, content=b"GLB-BYTES", headers={"content-type": "application/octet-stream"}
            )
        return httpx.Response(404)

    out = tmp_path / "assets" / "tree.glb"
    _client(handler).mesh("a low-poly tree", str(out))
    assert out.read_bytes() == b"GLB-BYTES"
    assert captured["body"]["prompt"] == "a low-poly tree"


def test_mesh_json_url_then_download(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/generate":
            return httpx.Response(
                200, json={"url": "/files/m.glb"}, headers={"content-type": "application/json"}
            )
        if request.url.path == "/files/m.glb":
            return httpx.Response(200, content=b"DOWNLOADED")
        return httpx.Response(404)

    out = tmp_path / "m.glb"
    _client(handler).mesh("a rock", str(out))
    assert out.read_bytes() == b"DOWNLOADED"


def test_get_mesh_generator_respects_url() -> None:
    assert get_mesh_generator(Config(assets=AssetsConfig(mesh_url=""))) is None
    gen = get_mesh_generator(Config(assets=AssetsConfig(mesh_url="http://localhost:8080")))
    assert isinstance(gen, MeshGenerator)


# -- the generate_asset tool's mesh path -----------------------------------------
class _FakeMesh:
    def available(self) -> bool:
        return True

    def mesh(self, prompt_or_image: str, out_path: str) -> None:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"MESH")


def _ctx(tmp_path, mesh_gen=None) -> ToolContext:
    return ToolContext(
        adapter=FakeAdapter(tmp_path / "game"), approver=AutoApprover(), mesh_generator=mesh_gen
    )


def test_generate_asset_mesh_falls_back_to_primitive(tmp_path) -> None:
    msg = execute(
        ToolCall(id="1", name="generate_asset", arguments={"prompt": "a tree", "kind": "mesh"}),
        _ctx(tmp_path, mesh_gen=None),
    )
    assert "primitive" in msg.lower()


def test_generate_asset_mesh_uses_backend_with_caveat(tmp_path) -> None:
    ctx = _ctx(tmp_path, mesh_gen=_FakeMesh())
    msg = execute(
        ToolCall(id="1", name="generate_asset", arguments={"prompt": "a low tree", "kind": "mesh"}),
        ctx,
    )
    assert "res://assets/a_low_tree.glb" in msg
    assert "cleanup" in msg.lower()  # the honest AI-3D caveat is surfaced
    assert (ctx.workspace / "assets" / "a_low_tree.glb").read_bytes() == b"MESH"
