"""Asset pipeline (optional) — local image/3D generation, degrades to placeholders."""

from __future__ import annotations

from playsmith.assets.base import AssetError, AssetGenerator, AssetKind, MeshGenerator
from playsmith.assets.comfyui import ComfyUIClient
from playsmith.assets.mesh import MeshClient
from playsmith.config import Config


def get_asset_generator(config: Config) -> AssetGenerator | None:
    """Return a 2D image generator if enabled in config, else None (=> placeholders).

    The CLI's explicit `assets generate` builds a client directly regardless of the flag,
    since the user asked for it.
    """
    if not config.assets.enabled:
        return None
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
    "get_asset_generator",
    "get_mesh_generator",
]
