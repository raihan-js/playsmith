"""The asset-generation abstraction.

Asset generation is **optional** (CLAUDE.md §5, docs/ARCHITECTURE.md §4): if no generator
is available, the agent uses colored placeholders and the game still ships. Nothing outside
``playsmith/assets/`` knows which backend (ComfyUI for 2D, Hunyuan3D/TRELLIS for 3D) is in use.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable


class AssetError(Exception):
    """Raised when asset generation fails (callers should fall back to placeholders)."""


class AssetKind(StrEnum):
    """What kind of art to generate — drives size and style hints."""

    SPRITE = "sprite"
    PORTRAIT = "portrait"
    BACKGROUND = "background"
    TILESET = "tileset"
    ICON = "icon"


@runtime_checkable
class AssetGenerator(Protocol):
    """Generates 2D game art locally. ``available()`` gates use; failures raise ``AssetError``."""

    def available(self) -> bool: ...
    def image(self, prompt: str, kind: AssetKind | str, out_path: str) -> None: ...


@runtime_checkable
class MeshGenerator(Protocol):
    """Generates 3D meshes locally (Phase 2). Output usually needs cleanup to be game-ready."""

    def available(self) -> bool: ...
    def mesh(self, prompt_or_image: str, out_path: str) -> None: ...
