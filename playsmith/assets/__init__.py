"""Asset pipeline (optional) — local image/3D generation, degrades to placeholders."""

from __future__ import annotations

from playsmith.assets.base import AssetError, AssetGenerator, AssetKind, MeshGenerator
from playsmith.assets.comfyui import ComfyUIClient
from playsmith.assets.mesh import MeshClient
from playsmith.assets.openai_image import OpenAIImageClient
from playsmith.config import Config


def get_asset_generator(config: Config) -> AssetGenerator | None:
    """Return a 2D image generator if enabled in config, else None (=> placeholders).

    `image_backend: openai` uses the OpenAI image API (falling back to the LLM key if no
    dedicated assets key is set); otherwise ComfyUI. The CLI's `assets generate` builds a
    client directly regardless of the `enabled` flag.
    """
    if not config.assets.enabled:
        return None
    if config.assets.image_backend == "openai":
        key = config.assets.openai_api_key or (
            config.llm.api_key if config.llm.provider == "openai" else ""
        )
        if not key:
            return None
        return OpenAIImageClient(
            key, base_url=config.assets.image_base_url, model=config.assets.image_model
        )
    return ComfyUIClient(config.assets.comfyui_url, model=config.assets.model)


def get_mesh_generator(config: Config) -> MeshGenerator | None:
    """Return a 3D mesh generator if a mesh backend is configured, else None (=> primitives)."""
    if not config.assets.mesh_url:
        return None
    return MeshClient(
        config.assets.mesh_url,
        backend=config.assets.mesh_backend,
        blender_path=config.assets.blender_path,
    )


__all__ = [
    "AssetError",
    "AssetGenerator",
    "AssetKind",
    "ComfyUIClient",
    "MeshClient",
    "MeshGenerator",
    "OpenAIImageClient",
    "get_asset_generator",
    "get_mesh_generator",
]
