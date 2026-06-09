"""Model catalog — power the studio's Settings/Models picker.

Two jobs, both UI-facing (CLAUDE.md §2 "tiered models"):

1. :func:`catalog` — describe the providers a user can pick from (a curated frontier/local set,
   plus live-discovered Ollama models), marking which one is active and whether each is *ready*
   (its API key is present). No model is ever called here; this is metadata only.
2. :func:`config_patch_for` — turn a UI pick ``(provider, model, key?)`` into a config patch that
   :func:`playsmith.config.save_runtime_patch` persists, so the choice sticks everywhere.

The frontier providers drive the director/critic; Ollama is the local tier for cheap sub-steps.
Provider ``kind`` selects the transport: ``anthropic`` → native ``/v1/messages``; everything else
→ the OpenAI-compatible ``/v1/chat/completions`` (CLAUDE.md §2).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

from playsmith.config import Config


@dataclass(frozen=True)
class ModelInfo:
    """One selectable model within a provider."""

    id: str
    label: str
    vision: bool = False  # can score rendered screenshots (the critic's future eyes)
    note: str = ""


@dataclass(frozen=True)
class ProviderInfo:
    """A provider the studio can point at, with its curated models."""

    id: str
    label: str
    kind: str  # "anthropic" (native) | "openai" (OpenAI-compatible /v1)
    base_url: str
    env_key: str  # the env var its API key comes from ("" for local/no-key)
    local: bool
    tier: str  # "frontier" | "local" | "cloud"
    models: list[ModelInfo] = field(default_factory=list)
    blurb: str = ""


# Curated providers. Frontier models drive the director/critic; Ollama is the local tier.
# Model ids are what each provider's API expects; keep the lists short and known-good.
KNOWN_PROVIDERS: tuple[ProviderInfo, ...] = (
    ProviderInfo(
        id="anthropic",
        label="Anthropic (Claude)",
        kind="anthropic",
        base_url="https://api.anthropic.com/v1",
        env_key="ANTHROPIC_API_KEY",
        local=False,
        tier="frontier",
        blurb="Frontier director/critic. The quality tier — recommended for the reasoning steps.",
        models=[
            ModelInfo("claude-opus-4-8", "Claude Opus 4.8", vision=True, note="most capable"),
            ModelInfo("claude-sonnet-4-6", "Claude Sonnet 4.6", vision=True, note="fast + strong"),
            ModelInfo("claude-haiku-4-5", "Claude Haiku 4.5", vision=True, note="cheapest"),
        ],
    ),
    ProviderInfo(
        id="openai",
        label="OpenAI",
        kind="openai",
        base_url="https://api.openai.com/v1",
        env_key="OPENAI_API_KEY",
        local=False,
        tier="frontier",
        blurb="GPT-4o family over the OpenAI-compatible API. Also powers art generation.",
        models=[
            ModelInfo("gpt-4o", "GPT-4o", vision=True),
            ModelInfo("gpt-4o-mini", "GPT-4o mini", vision=True, note="cheap"),
        ],
    ),
    ProviderInfo(
        id="nvidia",
        label="NVIDIA NIM",
        kind="openai",
        base_url="https://integrate.api.nvidia.com/v1",
        env_key="NVIDIA_API_KEY",
        local=False,
        tier="cloud",
        blurb="A strong frontier option if you don't have an Anthropic key (OpenAI-compatible).",
        models=[
            ModelInfo("meta/llama-3.3-70b-instruct", "Llama 3.3 70B"),
            ModelInfo(
                "meta/llama-3.2-90b-vision-instruct", "Llama 3.2 90B Vision", vision=True,
                note="critic-capable",
            ),
            ModelInfo("deepseek-ai/deepseek-r1", "DeepSeek-R1", note="reasoning"),
        ],
    ),
    ProviderInfo(
        id="openrouter",
        label="OpenRouter",
        kind="openai",
        base_url="https://openrouter.ai/api/v1",
        env_key="OPENROUTER_API_KEY",
        local=False,
        tier="cloud",
        blurb="One key, many models (OpenAI-compatible). Handy for mixing providers.",
        models=[
            ModelInfo("anthropic/claude-sonnet-4-6", "Claude Sonnet 4.6", vision=True),
            ModelInfo("openai/gpt-4o", "GPT-4o", vision=True),
            ModelInfo("meta-llama/llama-3.3-70b-instruct", "Llama 3.3 70B"),
        ],
    ),
    ProviderInfo(
        id="ollama",
        label="Ollama (local)",
        kind="openai",
        base_url="http://localhost:11434/v1",
        env_key="",
        local=True,
        tier="local",
        blurb="Self-hosted, free, private. The cheap sub-step tier — installed models appear here.",
        models=[  # fallbacks shown if Ollama isn't reachable for live discovery
            ModelInfo("qwen2.5-coder:7b", "qwen2.5-coder:7b", note="default"),
            ModelInfo("llama3.2", "llama3.2"),
            ModelInfo("llava", "llava", vision=True, note="vision"),
        ],
    ),
)

_BY_ID = {p.id: p for p in KNOWN_PROVIDERS}


def _ollama_root(base_url: str) -> str:
    """The Ollama server root (its native API lives at the root, not under ``/v1``)."""
    return base_url.rstrip("/").removesuffix("/v1").rstrip("/")


def discover_ollama(base_url: str, *, client: httpx.Client | None = None) -> list[ModelInfo]:
    """Live-list installed Ollama models via ``/api/tags``. Best-effort: ``[]`` if unreachable."""
    url = _ollama_root(base_url) + "/api/tags"
    try:
        getter = client.get if client is not None else httpx.get
        resp = getter(url, timeout=2.0)
        if resp.status_code != 200:
            return []
        models = resp.json().get("models") or []
    except (httpx.HTTPError, ValueError, KeyError, AttributeError):
        return []
    out: list[ModelInfo] = []
    for m in models:
        name = (m or {}).get("name") if isinstance(m, dict) else None
        if not name:
            continue
        vision = any(tag in name.lower() for tag in ("llava", "vision", "bakllava", "moondream"))
        out.append(ModelInfo(name, name, vision=vision))
    return out


def _key_present(provider: ProviderInfo) -> bool:
    """True if the provider needs no key, or its key is available in the environment."""
    return not provider.env_key or bool(os.environ.get(provider.env_key))


def _is_current(provider: ProviderInfo, cfg: Config) -> bool:
    return provider.id == cfg.llm.provider or (
        provider.kind == cfg.llm.kind
        and provider.base_url.rstrip("/") == cfg.llm.base_url.rstrip("/")
    )


def catalog(cfg: Config, *, client: httpx.Client | None = None) -> dict:
    """Describe selectable providers/models for the Settings UI (no model is called).

    Live-discovers Ollama models when reachable; everything else is the curated static set. Marks
    the active provider/model and whether each provider is *ready* (its API key is present).
    """
    providers: list[dict] = []
    for p in KNOWN_PROVIDERS:
        models = p.models
        if p.id == "ollama":
            discovered = discover_ollama(p.base_url, client=client)
            if discovered:
                models = discovered
        current = _is_current(p, cfg)
        providers.append(
            {
                "id": p.id,
                "label": p.label,
                "kind": p.kind,
                "base_url": p.base_url,
                "local": p.local,
                "tier": p.tier,
                "blurb": p.blurb,
                "needs_key": bool(p.env_key),
                "env_key": p.env_key,
                "ready": _key_present(p),
                "current": current,
                "models": [
                    {
                        "id": m.id,
                        "label": m.label,
                        "vision": m.vision,
                        "note": m.note,
                        "current": current and m.id == cfg.llm.model,
                    }
                    for m in models
                ],
            }
        )
    return {
        "current": {
            "provider": cfg.llm.provider,
            "model": cfg.llm.model,
            "kind": cfg.llm.kind,
            "where": "local" if cfg.llm.is_local else "cloud",
        },
        "providers": providers,
    }


def config_patch_for(
    provider: str,
    model: str,
    api_key: str | None = None,
    base_url: str | None = None,
) -> dict:
    """Build the ``{"llm": {...}}`` patch for a UI model pick (persist via ``save_runtime_patch``).

    Resolves ``kind``/``base_url`` from the known provider when recognised; a custom provider needs
    an explicit ``base_url``. The API key is taken from ``api_key`` if given, else from the
    provider's env var, and stored literally so the next ``load_config`` picks it up everywhere.
    """
    provider = (provider or "").strip()
    model = (model or "").strip()
    if not provider or not model:
        raise ValueError("provider and model are required")
    known = _BY_ID.get(provider)
    resolved_base = (base_url or "").strip() or (known.base_url if known else "")
    if not resolved_base:
        raise ValueError(f"Unknown provider '{provider}' needs an explicit base_url.")
    kind = known.kind if known else "openai"
    key = api_key if api_key is not None else (os.environ.get(known.env_key, "") if known else "")
    llm: dict = {
        "provider": provider,
        "base_url": resolved_base,
        "model": model,
        "kind": kind,
    }
    if key:
        llm["api_key"] = key
    return {"llm": llm}
