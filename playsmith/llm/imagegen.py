"""Art/texture generation — turn a text prompt into a real image for a UE project.

Playsmith's old (Godot-era) flow generated game art; the re-founding dropped it. This brings it
back for the Unreal flow: generate concept art / textures via the OpenAI-compatible Images API
(``/v1/images/generations``) and save them *into the project* so they can be imported in the UE
editor (the dressed level is a real project the user fully owns — CLAUDE.md §1).

It's deliberately small and provider-agnostic over the OpenAI image shape. The provider is resolved
from the environment / config (:func:`resolve_image_provider`); when none is available the studio
shows a "set an OpenAI key" hint instead of a dead "not supported" message.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass

import httpx

from playsmith.config import Config

# Default image model + a couple of standard sizes. Override the model with $PLAYSMITH_IMAGE_MODEL.
_DEFAULT_MODEL = "gpt-image-1"
VALID_SIZES = ("1024x1024", "1536x1024", "1024x1536")


class ImageGenError(Exception):
    """Raised when image generation is unavailable or the provider call fails."""


@dataclass(frozen=True)
class ImageProvider:
    """Where to generate images: an OpenAI-compatible ``/v1`` endpoint + key + model."""

    base_url: str
    api_key: str
    model: str


def resolve_image_provider(cfg: Config | None = None) -> ImageProvider | None:
    """Pick an image provider, or ``None`` if art generation isn't configured.

    Order: an explicit ``OPENAI_API_KEY`` (the most reliable for the Images API), else the active
    LLM provider when it is an OpenAI-compatible cloud endpoint that carries a key. Local model
    runners generally don't serve ``/images/generations``, so they're skipped.
    """
    model = os.environ.get("PLAYSMITH_IMAGE_MODEL", _DEFAULT_MODEL)
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return ImageProvider("https://api.openai.com/v1", key, model)
    if cfg is not None:
        llm = cfg.llm
        if llm.api_key and llm.kind == "openai" and "openai.com" in llm.base_url:
            return ImageProvider(llm.base_url.rstrip("/"), llm.api_key, model)
    return None


def generate_image(
    provider: ImageProvider,
    prompt: str,
    *,
    size: str = "1024x1024",
    client: httpx.Client | None = None,
    timeout: float = 180.0,
) -> bytes:
    """Generate one image and return its PNG bytes. Raises :class:`ImageGenError` on any failure.

    Handles both response shapes the Images API returns: inline ``b64_json`` (gpt-image-1) and a
    hosted ``url`` (dall-e style), fetching the latter.
    """
    if not prompt or not prompt.strip():
        raise ImageGenError("An art prompt is required.")
    size = size if size in VALID_SIZES else "1024x1024"
    url = provider.base_url.rstrip("/") + "/images/generations"
    payload = {"model": provider.model, "prompt": prompt.strip()[:1000], "n": 1, "size": size}
    headers = {"Authorization": f"Bearer {provider.api_key}", "Content-Type": "application/json"}
    try:
        poster = client.post if client is not None else httpx.post
        resp = poster(url, json=payload, headers=headers, timeout=timeout)
    except httpx.HTTPError as exc:
        raise ImageGenError(f"Could not reach the image endpoint at {url}: {exc}") from exc
    if resp.status_code >= 400:
        raise ImageGenError(f"Image endpoint returned HTTP {resp.status_code}: {resp.text[:300]}")
    try:
        item = (resp.json().get("data") or [{}])[0]
    except (ValueError, AttributeError, IndexError) as exc:
        raise ImageGenError("Image endpoint returned an unexpected response.") from exc
    if item.get("b64_json"):
        try:
            return base64.b64decode(item["b64_json"])
        except (ValueError, TypeError) as exc:
            raise ImageGenError("Image endpoint returned undecodable image data.") from exc
    if item.get("url"):
        try:
            getter = client.get if client is not None else httpx.get
            img = getter(item["url"], timeout=timeout)
            if img.status_code >= 400:
                raise ImageGenError(f"Could not download the generated image ({img.status_code}).")
            return img.content
        except httpx.HTTPError as exc:
            raise ImageGenError(f"Could not download the generated image: {exc}") from exc
    raise ImageGenError("Image endpoint returned no image.")
