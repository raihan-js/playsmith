"""OpenAI image-generation backend (gpt-image-1 / DALL·E) for game sprites + backgrounds.

Lets the agent generate real art from the user's existing OpenAI key — no GPU or ComfyUI. Like
the rest of the asset pipeline it's optional and degrades to placeholders (CLAUDE.md §5).
"""

from __future__ import annotations

import base64
from pathlib import Path

import httpx

from playsmith.assets.base import AssetError

# Pixel sizes the OpenAI image API accepts, chosen per asset kind.
_SIZES = {
    "sprite": "1024x1024",
    "icon": "1024x1024",
    "portrait": "1024x1536",
    "background": "1536x1024",
    "tileset": "1024x1024",
}
_TRANSPARENT_KINDS = {"sprite", "icon", "portrait", "tileset"}


def _style(prompt: str, kind: str) -> str:
    if kind in ("sprite", "icon"):
        return (
            f"{prompt}, a clean game sprite, centered, transparent background, no text, no border"
        )
    if kind == "background":
        return f"{prompt}, a wide game background scene, no characters, no text, no UI"
    if kind == "tileset":
        return f"{prompt}, a seamless game tile, top-down, transparent background, no text"
    return prompt


class OpenAIImageClient:
    """An :class:`~playsmith.assets.base.AssetGenerator` backed by the OpenAI image API."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-image-1",
        timeout: float = 180.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._client = client

    def available(self) -> bool:
        return bool(self.api_key)

    def image(self, prompt: str, kind: str, out_path: str) -> None:
        kind = str(kind)
        body: dict = {
            "model": self.model,
            "prompt": _style(prompt, kind),
            "size": _SIZES.get(kind, "1024x1024"),
            "n": 1,
        }
        if "dall-e" in self.model:
            body["response_format"] = "b64_json"  # gpt-image-1 returns b64 by default
        elif kind in _TRANSPARENT_KINDS:
            body["background"] = "transparent"  # gpt-image-1 supports transparent PNGs

        url = self.base_url + "/images/generations"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            poster = self._client.post if self._client is not None else httpx.post
            resp = poster(url, json=body, headers=headers, timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise AssetError(f"Could not reach the OpenAI image API: {exc}") from exc
        if resp.status_code >= 400:
            raise AssetError(f"OpenAI image API HTTP {resp.status_code}: {resp.text[:300]}")

        item = (resp.json().get("data") or [{}])[0]
        if item.get("b64_json"):
            raw = base64.b64decode(item["b64_json"])
        elif item.get("url"):
            getter = self._client.get if self._client is not None else httpx.get
            raw = getter(item["url"], timeout=self.timeout).content
        else:
            raise AssetError("OpenAI image API returned no image data.")

        out = Path(out_path).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(raw)
