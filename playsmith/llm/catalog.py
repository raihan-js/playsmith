"""Model discovery + local-model management for the Settings UI.

Lets the web UI behave like other AI tools: see which providers are reachable, list their models,
paste an API key, or download a local model — all without editing YAML. Everything an LLM call
needs still flows from :mod:`playsmith.config`; this module only *discovers* and *pulls*.

Three provider families, all OpenAI-compatible for chat (so one gateway covers them):
  - ``openai``     — cloud, needs an API key. Lists via ``GET /v1/models``.
  - ``openrouter`` — cloud aggregator, needs a key. Lists via its public ``/models`` (no key).
  - ``ollama``     — local, no key. Lists installed via ``/api/tags``; downloads via ``/api/pull``.
A ``custom`` family covers any other OpenAI-compatible ``base_url`` (LM Studio, vLLM, LocalAI…).
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx

from playsmith.config import Config

# Sensible defaults per provider so the UI can configure one with a single click.
PROVIDER_PRESETS: dict[str, dict] = {
    "openai": {
        "label": "OpenAI",
        "kind": "cloud",
        "base_url": "https://api.openai.com/v1",
        "needs_key": True,
        "key_url": "https://platform.openai.com/api-keys",
    },
    "openrouter": {
        "label": "OpenRouter",
        "kind": "cloud",
        "base_url": "https://openrouter.ai/api/v1",
        "needs_key": True,
        "key_url": "https://openrouter.ai/keys",
    },
    "ollama": {
        "label": "Ollama (local)",
        "kind": "local",
        "base_url": "http://localhost:11434/v1",
        "needs_key": False,
        "key_url": "https://ollama.com/download",
    },
    "custom": {
        "label": "Custom (OpenAI-compatible)",
        "kind": "local",
        "base_url": "http://localhost:8000/v1",
        "needs_key": False,
        "key_url": "",
    },
}

# Curated fallbacks so the picker is useful even offline / before a key is set.
_OPENAI_FALLBACK = ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "o4-mini"]
_OPENROUTER_FALLBACK = [
    "anthropic/claude-3.5-sonnet",
    "openai/gpt-4o",
    "google/gemini-2.0-flash-001",
    "meta-llama/llama-3.1-70b-instruct",
    "qwen/qwen-2.5-coder-32b-instruct",
    "deepseek/deepseek-chat",
]
# Good local coder models to offer for one-click download (agentic file editing needs decent tools).
OLLAMA_SUGGESTED = [
    {"name": "qwen2.5-coder:7b", "size": "~4.7 GB", "note": "Recommended — strong small coder"},
    {"name": "qwen2.5-coder:14b", "size": "~9 GB", "note": "Better, needs more RAM/VRAM"},
    {"name": "llama3.1:8b", "size": "~4.7 GB", "note": "General-purpose, reliable tools"},
    {"name": "deepseek-coder-v2:16b", "size": "~8.9 GB", "note": "Code-focused MoE"},
    {"name": "mistral:7b", "size": "~4.1 GB", "note": "Fast, lightweight"},
]


def ollama_base(cfg: Config) -> str:
    """The native Ollama host (no ``/v1``). Derived from config if Ollama is the active provider."""
    url = cfg.llm.base_url
    if "11434" in url or cfg.llm.provider.lower() == "ollama":
        return url.split("/v1")[0].rstrip("/")
    return "http://localhost:11434"


def _get_json(url: str, *, headers: dict | None = None, timeout: float = 4.0) -> dict | list | None:
    try:
        resp = httpx.get(url, headers=headers or {}, timeout=timeout)
        if resp.status_code == 200:
            return resp.json()
    except (httpx.HTTPError, ValueError):
        return None
    return None


def ollama_installed(base: str) -> list[str]:
    """Model names already pulled locally, via ``GET /api/tags``. Empty if Ollama isn't running."""
    data = _get_json(f"{base}/api/tags")
    if isinstance(data, dict) and isinstance(data.get("models"), list):
        return [m.get("name", "") for m in data["models"] if m.get("name")]
    return []


def _openai_models(base_url: str, api_key: str) -> list[str]:
    if not api_key:
        return list(_OPENAI_FALLBACK)
    data = _get_json(
        f"{base_url.rstrip('/')}/models", headers={"Authorization": f"Bearer {api_key}"}
    )
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        ids = [m.get("id", "") for m in data["data"] if isinstance(m, dict)]
        chat = sorted(i for i in ids if i.startswith(("gpt-", "o1", "o3", "o4", "chatgpt")))
        return chat or list(_OPENAI_FALLBACK)
    return list(_OPENAI_FALLBACK)


def _openrouter_models(api_key: str) -> list[str]:
    data = _get_json("https://openrouter.ai/api/v1/models")
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        ids = [m.get("id", "") for m in data["data"] if isinstance(m, dict) and m.get("id")]
        if ids:
            # Keep it bounded but include the curated favourites first.
            favs = [m for m in _OPENROUTER_FALLBACK if m in ids]
            rest = [m for m in ids if m not in favs]
            return favs + rest[:40]
    return list(_OPENROUTER_FALLBACK)


def catalog(cfg: Config) -> dict:
    """Everything the Settings panel needs: the active model + each provider's reachable models."""
    o_base = ollama_base(cfg)
    installed = ollama_installed(o_base)
    openai_key = cfg.llm.api_key if cfg.llm.provider == "openai" else ""
    providers = [
        {
            "id": "openai",
            "label": PROVIDER_PRESETS["openai"]["label"],
            "kind": "cloud",
            "needs_key": True,
            "has_key": bool(openai_key),
            "base_url": PROVIDER_PRESETS["openai"]["base_url"],
            "key_url": PROVIDER_PRESETS["openai"]["key_url"],
            "models": _openai_models(PROVIDER_PRESETS["openai"]["base_url"], openai_key),
        },
        {
            "id": "openrouter",
            "label": PROVIDER_PRESETS["openrouter"]["label"],
            "kind": "cloud",
            "needs_key": True,
            "has_key": cfg.llm.provider == "openrouter" and bool(cfg.llm.api_key),
            "base_url": PROVIDER_PRESETS["openrouter"]["base_url"],
            "key_url": PROVIDER_PRESETS["openrouter"]["key_url"],
            "models": _openrouter_models(""),
        },
        {
            "id": "ollama",
            "label": PROVIDER_PRESETS["ollama"]["label"],
            "kind": "local",
            "needs_key": False,
            "has_key": True,
            "base_url": PROVIDER_PRESETS["ollama"]["base_url"],
            "key_url": PROVIDER_PRESETS["ollama"]["key_url"],
            "running": bool(installed) or _get_json(f"{o_base}/api/tags") is not None,
            "installed": installed,
            "suggested": OLLAMA_SUGGESTED,
            "models": installed,
        },
    ]
    return {
        "active": {
            "provider": cfg.llm.provider,
            "model": cfg.llm.model,
            "base_url": cfg.llm.base_url,
            "where": "local" if cfg.llm.is_local else "cloud",
        },
        "providers": providers,
    }


def config_patch_for(provider: str, model: str, api_key: str | None, base_url: str | None) -> dict:
    """Build the config override for selecting a provider/model (+ optional key/base_url)."""
    preset = PROVIDER_PRESETS.get(provider, PROVIDER_PRESETS["custom"])
    llm: dict = {
        "provider": provider,
        "model": model,
        "base_url": base_url or preset["base_url"],
        "kind": "openai",
    }
    if api_key is not None and api_key != "":
        llm["api_key"] = api_key
    patch: dict = {"llm": llm}
    # If selecting OpenAI and a key is given, let the OpenAI image backend use it too.
    if provider == "openai" and api_key:
        patch["assets"] = {"image_backend": "openai", "openai_api_key": api_key, "enabled": True}
    return patch


def pull_ollama(base: str, model: str) -> Iterator[dict]:
    """Stream an Ollama model download. Yields ``{status, completed, total, percent}`` dicts."""
    try:
        with httpx.stream(
            "POST",
            f"{base}/api/pull",
            json={"name": model, "stream": True},
            timeout=None,
        ) as resp:
            if resp.status_code != 200:
                yield {"status": "error", "error": f"HTTP {resp.status_code}", "done": True}
                return
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                total = msg.get("total") or 0
                completed = msg.get("completed") or 0
                percent = round(completed / total * 100) if total else None
                yield {
                    "status": msg.get("status", ""),
                    "completed": completed,
                    "total": total,
                    "percent": percent,
                    "error": msg.get("error"),
                    "done": msg.get("status") == "success",
                }
    except httpx.HTTPError as exc:
        yield {"status": "error", "error": str(exc), "done": True}
