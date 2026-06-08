"""Asset pipeline (optional) — local image/3D generation, degrades to placeholders."""

from __future__ import annotations

from playsmith.assets.base import AssetError, AssetGenerator, AssetKind
from playsmith.assets.comfyui import ComfyUIClient
from playsmith.config import Config


def get_asset_generator(config: Config) -> AssetGenerator | None:
    """Return a generator if asset generation is enabled in config, else None.

    None means "use placeholders". The CLI's explicit `assets generate` builds a client
    directly regardless of the flag, since the user asked for it.
    """
    if not config.assets.enabled:
        return None
    return ComfyUIClient(config.assets.comfyui_url, model=config.assets.model)


__all__ = [
    "AssetError",
    "AssetGenerator",
    "AssetKind",
    "ComfyUIClient",
    "get_asset_generator",
]
