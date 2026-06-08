"""3D mesh generation (Phase 2) — Hunyuan3D / TRELLIS style backends, optional.

AI 3D output is **not** finished art: it usually needs topology / UV / scale / rigging cleanup
before it's game-ready. We surface that caveat every time (docs/ARCHITECTURE.md §4, WHY.md risk
#1 — never over-promise). Like the 2D pipeline, this is optional: no backend -> the agent uses
primitive meshes (BoxMesh/CapsuleMesh) and the game still ships.

Backends vary (Hunyuan3D 2.1 is Apache-2.0, TRELLIS is MIT; both are commonly served behind a
small HTTP wrapper). This client speaks a simple generic contract — adjust per backend if needed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import httpx

from playsmith.assets.base import AssetError

MESH_CAVEAT = (
    "AI-generated 3D meshes usually need cleanup (topology / UVs / scale / rigging) before they "
    "are truly game-ready. Treat this as a starting point, not a finished asset."
)

# Best-effort Blender headless cleanup: import, decimate to half, re-export.
_BLENDER_CLEANUP = (
    "import bpy, os\n"
    "p = os.environ.get('PLAYSMITH_MESH', '')\n"
    "ext = os.path.splitext(p)[1].lower()\n"
    "bpy.ops.wm.read_factory_settings(use_empty=True)\n"
    "if ext in ('.glb', '.gltf'): bpy.ops.import_scene.gltf(filepath=p)\n"
    "elif ext == '.obj': bpy.ops.wm.obj_import(filepath=p)\n"
    "for o in bpy.context.scene.objects:\n"
    "    if o.type == 'MESH':\n"
    "        m = o.modifiers.new('decimate', 'DECIMATE'); m.ratio = 0.5\n"
    "if ext in ('.glb', '.gltf'): bpy.ops.export_scene.gltf(filepath=p)\n"
)


class MeshClient:
    """A :class:`~playsmith.assets.base.MeshGenerator` backed by an HTTP mesh server."""

    def __init__(
        self,
        base_url: str = "",
        *,
        backend: str = "hunyuan3d",
        out_format: str = "glb",
        blender_path: str = "blender",
        timeout: float = 600.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.backend = backend
        self.out_format = out_format
        self.blender_path = blender_path
        self.timeout = timeout
        self._client = client

    def _get(self, url: str, **kwargs) -> httpx.Response:
        if self._client is not None:
            return self._client.get(url, timeout=self.timeout, **kwargs)
        return httpx.get(url, timeout=self.timeout, **kwargs)

    def _post(self, path: str, json: dict) -> httpx.Response:
        url = self.base_url + path
        if self._client is not None:
            return self._client.post(url, json=json, timeout=self.timeout)
        return httpx.post(url, json=json, timeout=self.timeout)

    def available(self) -> bool:
        if not self.base_url:
            return False
        try:
            return self._get(self.base_url + "/health").status_code == 200
        except httpx.HTTPError:
            return False

    def mesh(self, prompt_or_image: str, out_path: str) -> None:
        resp = self._post(
            "/generate",
            {"prompt": prompt_or_image, "format": self.out_format, "backend": self.backend},
        )
        if resp.status_code >= 400:
            raise AssetError(f"mesh backend /generate failed (HTTP {resp.status_code}).")
        data = resp.content
        if "application/json" in resp.headers.get("content-type", ""):
            payload = resp.json()
            mesh_url = payload.get("url") or payload.get("mesh_url")
            if not mesh_url:
                raise AssetError("mesh backend returned no mesh URL.")
            full = mesh_url if mesh_url.startswith("http") else self.base_url + mesh_url
            data = self._get(full).content
        out = Path(out_path).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        self._cleanup(out)

    def _cleanup(self, mesh_path: Path) -> None:
        """Optionally decimate/normalize via Blender headless. Skipped if Blender is absent."""
        if not shutil.which(self.blender_path):
            return
        try:
            subprocess.run(
                [self.blender_path, "--background", "--python-expr", _BLENDER_CLEANUP],
                capture_output=True,
                timeout=120,
                env={**os.environ, "PLAYSMITH_MESH": str(mesh_path)},
            )
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            pass  # best-effort cleanup; the raw mesh is still usable
