"""ComfyUI 2D asset generator (text -> sprite/background image).

Talks to a local ComfyUI server's HTTP API: submit a text2img workflow to ``/prompt``, poll
``/history/{id}`` until the image is rendered, then download it from ``/view``. ComfyUI is never
a hard dependency — ``available()`` returns False when the server isn't reachable, and callers
fall back to placeholders (CLAUDE.md §5).
"""

from __future__ import annotations

import time
from pathlib import Path

import httpx

from playsmith.assets.base import AssetError

# Pixel dimensions per asset kind.
_KIND_SIZES = {
    "sprite": (512, 512),
    "portrait": (768, 1024),
    "background": (1024, 576),
    "tileset": (512, 512),
    "icon": (256, 256),
}
_DEFAULT_NEGATIVE = "blurry, low quality, watermark, text, jpeg artifacts, extra limbs"


def default_workflow(
    prompt: str, *, model: str, width: int, height: int, seed: int, negative: str
) -> dict:
    """A minimal SDXL text2img workflow in ComfyUI's API (node-graph) format."""
    return {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": model}},
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["4", 1]}},
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": 25,
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "playsmith", "images": ["8", 0]},
        },
    }


class ComfyUIClient:
    """An :class:`~playsmith.assets.base.AssetGenerator` backed by a local ComfyUI server."""

    def __init__(
        self,
        base_url: str = "http://localhost:8188",
        *,
        model: str = "sd_xl_base_1.0.safetensors",
        negative_prompt: str = _DEFAULT_NEGATIVE,
        timeout: float = 300.0,
        poll_interval: float = 1.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.negative_prompt = negative_prompt
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._client = client

    # -- HTTP helpers ----------------------------------------------------------
    def _get(self, path: str, **kwargs) -> httpx.Response:
        url = self.base_url + path
        if self._client is not None:
            return self._client.get(url, timeout=self.timeout, **kwargs)
        return httpx.get(url, timeout=self.timeout, **kwargs)

    def _post(self, path: str, json: dict) -> httpx.Response:
        url = self.base_url + path
        if self._client is not None:
            return self._client.post(url, json=json, timeout=self.timeout)
        return httpx.post(url, json=json, timeout=self.timeout)

    # -- AssetGenerator --------------------------------------------------------
    def available(self) -> bool:
        try:
            return self._get("/system_stats").status_code == 200
        except httpx.HTTPError:
            return False

    def image(self, prompt: str, kind: str, out_path: str) -> None:
        kind = str(kind)
        width, height = _KIND_SIZES.get(kind, (512, 512))
        styled = prompt + (", pixel art, crisp pixels, game sprite" if kind == "sprite" else "")
        workflow = default_workflow(
            styled,
            model=self.model,
            width=width,
            height=height,
            seed=0,
            negative=self.negative_prompt,
        )
        prompt_id = self._submit(workflow)
        images = self._await_images(prompt_id)
        if not images:
            raise AssetError("ComfyUI returned no images.")
        data = self._download(images[0])
        out = Path(out_path).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)

    def mesh(self, prompt_or_image: str, out_path: str) -> None:
        raise NotImplementedError("3D mesh generation lands in Phase 2 (Hunyuan3D/TRELLIS).")

    # -- workflow plumbing -----------------------------------------------------
    def _submit(self, workflow: dict) -> str:
        resp = self._post("/prompt", {"prompt": workflow})
        if resp.status_code >= 400:
            raise AssetError(f"ComfyUI /prompt failed (HTTP {resp.status_code}): {resp.text[:300]}")
        prompt_id = resp.json().get("prompt_id")
        if not prompt_id:
            raise AssetError("ComfyUI did not return a prompt_id.")
        return prompt_id

    def _await_images(self, prompt_id: str) -> list[dict]:
        deadline = self.timeout / max(self.poll_interval, 0.01)
        attempts = 0
        while attempts <= deadline:
            history = self._get(f"/history/{prompt_id}").json()
            entry = history.get(prompt_id)
            if entry:
                images: list[dict] = []
                for node_output in (entry.get("outputs") or {}).values():
                    images.extend(node_output.get("images") or [])
                return images
            attempts += 1
            time.sleep(self.poll_interval)
        raise AssetError(f"ComfyUI render timed out after {self.timeout}s.")

    def _download(self, image: dict) -> bytes:
        params = {
            "filename": image.get("filename", ""),
            "subfolder": image.get("subfolder", ""),
            "type": image.get("type", "output"),
        }
        resp = self._get("/view", params=params)
        if resp.status_code >= 400:
            raise AssetError(f"ComfyUI /view failed (HTTP {resp.status_code}).")
        return resp.content
