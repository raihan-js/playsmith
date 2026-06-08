"""Configuration loading for Playsmith.

The single source of runtime configuration is ``config/playsmith.yaml`` (copied from
``config/playsmith.example.yaml``). Nothing else in the codebase should hard-code model
names, endpoints, or paths — they all flow from here. See CLAUDE.md §6.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import yaml

# Repo root = two levels up from this file (playsmith/config.py -> repo/).
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "config" / "playsmith.yaml"
EXAMPLE_CONFIG = REPO_ROOT / "config" / "playsmith.example.yaml"

_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")

# Provider names / hosts treated as "local" — used to decide when a router crossing
# to a cloud provider must warn the user (CLAUDE.md §5).
_LOCAL_PROVIDERS = frozenset(
    {
        "ollama",
        "lmstudio",
        "lm-studio",
        "lm_studio",
        "vllm",
        "localai",
        "local-ai",
        "llamacpp",
        "llama.cpp",
        "llama-cpp",
        "koboldcpp",
        "text-generation-webui",
    }
)
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "::1"})


def _is_local_endpoint(base_url: str, provider: str) -> bool:
    host = (urlparse(base_url).hostname or "").lower()
    if host in _LOCAL_HOSTS:
        return True
    if host.startswith(("192.168.", "10.")):  # private LAN ranges
        return True
    return provider.lower() in _LOCAL_PROVIDERS


class ConfigError(Exception):
    """Raised when configuration is missing or malformed."""


def _expand(value: str) -> str:
    """Expand ``~`` and ``${ENV_VAR}`` references in a string value."""
    if not isinstance(value, str):
        return value

    def _sub(match: re.Match[str]) -> str:
        return os.environ.get(match.group(1), "")

    return os.path.expanduser(_ENV_PATTERN.sub(_sub, value))


@dataclass
class LLMConfig:
    """A single LLM provider.

    Reached via the OpenAI-compatible ``/v1/chat/completions`` (``kind="openai"``, the default —
    covers Ollama, LM Studio, vLLM, OpenAI, OpenRouter, Gemini-compat) or Anthropic's native
    ``/v1/messages`` (``kind="anthropic"``).
    """

    provider: str = "ollama"
    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen2.5-coder:7b"
    api_key: str = ""
    num_ctx: int = 16384
    kind: str = "openai"

    @property
    def is_local(self) -> bool:
        """True if this endpoint is a local/self-hosted model (no cloud-crossing warning needed)."""
        return _is_local_endpoint(self.base_url, self.provider)

    @classmethod
    def from_dict(cls, data: dict) -> LLMConfig:
        return cls(
            provider=data.get("provider", "ollama"),
            base_url=data.get("base_url", "http://localhost:11434/v1"),
            model=data.get("model", "qwen2.5-coder:7b"),
            api_key=_expand(data.get("api_key", "") or ""),
            num_ctx=int(data.get("num_ctx", 16384)),
            kind=str(data.get("kind", "openai")).lower(),
        )


@dataclass
class GodotConfig:
    binary: str = "godot"
    version: str = "4"

    @classmethod
    def from_dict(cls, data: dict) -> GodotConfig:
        return cls(
            binary=_expand(data.get("binary", "godot")),
            version=str(data.get("version", "4")),
        )


@dataclass
class EngineConfig:
    default: str = "godot"
    godot: GodotConfig = field(default_factory=GodotConfig)

    @classmethod
    def from_dict(cls, data: dict) -> EngineConfig:
        return cls(
            default=data.get("default", "godot"),
            godot=GodotConfig.from_dict(data.get("godot", {}) or {}),
        )


@dataclass
class AssetsConfig:
    enabled: bool = False
    comfyui_url: str = "http://localhost:8188"
    model: str = "sd_xl_base_1.0.safetensors"
    mesh_url: str = ""  # 3D mesh backend (Hunyuan3D/TRELLIS); empty => primitives only
    mesh_backend: str = "hunyuan3d"
    blender_path: str = "blender"

    @classmethod
    def from_dict(cls, data: dict) -> AssetsConfig:
        return cls(
            enabled=bool(data.get("enabled", False)),
            comfyui_url=data.get("comfyui_url", "http://localhost:8188"),
            model=data.get("model", "sd_xl_base_1.0.safetensors"),
            mesh_url=data.get("mesh_url", "") or "",
            mesh_backend=data.get("mesh_backend", "hunyuan3d"),
            blender_path=_expand(data.get("blender_path", "blender")),
        )


@dataclass
class PublishConfig:
    butler_path: str = "butler"

    @classmethod
    def from_dict(cls, data: dict) -> PublishConfig:
        itch = data.get("itch", {}) or {}
        return cls(butler_path=_expand(itch.get("butler_path", "butler")))


@dataclass
class SkillsConfig:
    # The curated community skill index (Phase 2). Local install dir for downloaded skills.
    registry_url: str = (
        "https://raw.githubusercontent.com/raihan-js/playsmith-skills/main/index.json"
    )
    dir: str = "~/.playsmith/skills"

    @classmethod
    def from_dict(cls, data: dict) -> SkillsConfig:
        return cls(
            registry_url=data.get(
                "registry_url",
                "https://raw.githubusercontent.com/raihan-js/playsmith-skills/main/index.json",
            ),
            dir=_expand(data.get("dir", "~/.playsmith/skills")),
        )


@dataclass
class Config:
    """The fully-resolved Playsmith configuration."""

    workspace_dir: Path = field(default_factory=lambda: Path.home() / "playsmith-games")
    llm: LLMConfig = field(default_factory=LLMConfig)
    # Optional model router (Phase 1): per-task provider overrides + a cloud fallback.
    llm_routes: dict[str, LLMConfig] = field(default_factory=dict)
    llm_fallback: LLMConfig | None = None
    engine: EngineConfig = field(default_factory=EngineConfig)
    assets: AssetsConfig = field(default_factory=AssetsConfig)
    publish: PublishConfig = field(default_factory=PublishConfig)
    skills: SkillsConfig = field(default_factory=SkillsConfig)
    source_path: Path | None = None

    @classmethod
    def from_dict(cls, data: dict, source_path: Path | None = None) -> Config:
        workspace = _expand(data.get("workspace_dir", "~/playsmith-games"))
        llm_raw = data.get("llm", {}) or {}
        routes = {
            str(name): LLMConfig.from_dict(spec or {})
            for name, spec in (llm_raw.get("routes") or {}).items()
        }
        fallback_raw = llm_raw.get("fallback")
        fallback = LLMConfig.from_dict(fallback_raw) if fallback_raw else None
        return cls(
            workspace_dir=Path(workspace),
            llm=LLMConfig.from_dict(llm_raw),
            llm_routes=routes,
            llm_fallback=fallback,
            engine=EngineConfig.from_dict(data.get("engine", {}) or {}),
            assets=AssetsConfig.from_dict(data.get("assets", {}) or {}),
            publish=PublishConfig.from_dict(data.get("publish", {}) or {}),
            skills=SkillsConfig.from_dict(data.get("skills", {}) or {}),
            source_path=source_path,
        )


def _resolve_config_path(path: str | os.PathLike[str] | None) -> Path:
    """Pick which config file to load.

    Priority: explicit ``path`` arg > ``$PLAYSMITH_CONFIG`` > ``config/playsmith.yaml``
    > ``config/playsmith.example.yaml`` (so the tool is usable before the user copies
    the example, and tests don't need a local config).
    """
    if path is not None:
        return Path(path)
    env = os.environ.get("PLAYSMITH_CONFIG")
    if env:
        return Path(env)
    if DEFAULT_CONFIG.exists():
        return DEFAULT_CONFIG
    return EXAMPLE_CONFIG


def load_config(path: str | os.PathLike[str] | None = None) -> Config:
    """Load and resolve configuration from YAML.

    Raises ``ConfigError`` if the chosen file does not exist or is not a mapping.
    """
    config_path = _resolve_config_path(path)
    if not config_path.exists():
        raise ConfigError(
            f"No config found at {config_path}. "
            "Copy config/playsmith.example.yaml to config/playsmith.yaml and edit it."
        )
    try:
        raw = yaml.safe_load(config_path.read_text()) or {}
    except yaml.YAMLError as exc:  # pragma: no cover - defensive
        raise ConfigError(f"Failed to parse {config_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(
            f"Config root in {config_path} must be a mapping, got {type(raw).__name__}."
        )
    return Config.from_dict(raw, source_path=config_path)
