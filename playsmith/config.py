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

import yaml

# Repo root = two levels up from this file (playsmith/config.py -> repo/).
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "config" / "playsmith.yaml"
EXAMPLE_CONFIG = REPO_ROOT / "config" / "playsmith.example.yaml"

_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


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
    """A single LLM provider, reached via the OpenAI-compatible /v1 API."""

    provider: str = "ollama"
    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen2.5-coder:7b"
    api_key: str = ""
    num_ctx: int = 16384

    @classmethod
    def from_dict(cls, data: dict) -> LLMConfig:
        return cls(
            provider=data.get("provider", "ollama"),
            base_url=data.get("base_url", "http://localhost:11434/v1"),
            model=data.get("model", "qwen2.5-coder:7b"),
            api_key=_expand(data.get("api_key", "") or ""),
            num_ctx=int(data.get("num_ctx", 16384)),
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

    @classmethod
    def from_dict(cls, data: dict) -> AssetsConfig:
        return cls(
            enabled=bool(data.get("enabled", False)),
            comfyui_url=data.get("comfyui_url", "http://localhost:8188"),
        )


@dataclass
class PublishConfig:
    butler_path: str = "butler"

    @classmethod
    def from_dict(cls, data: dict) -> PublishConfig:
        itch = data.get("itch", {}) or {}
        return cls(butler_path=_expand(itch.get("butler_path", "butler")))


@dataclass
class Config:
    """The fully-resolved Playsmith configuration."""

    workspace_dir: Path = field(default_factory=lambda: Path.home() / "playsmith-games")
    llm: LLMConfig = field(default_factory=LLMConfig)
    engine: EngineConfig = field(default_factory=EngineConfig)
    assets: AssetsConfig = field(default_factory=AssetsConfig)
    publish: PublishConfig = field(default_factory=PublishConfig)
    source_path: Path | None = None

    @classmethod
    def from_dict(cls, data: dict, source_path: Path | None = None) -> Config:
        workspace = _expand(data.get("workspace_dir", "~/playsmith-games"))
        return cls(
            workspace_dir=Path(workspace),
            llm=LLMConfig.from_dict(data.get("llm", {}) or {}),
            engine=EngineConfig.from_dict(data.get("engine", {}) or {}),
            assets=AssetsConfig.from_dict(data.get("assets", {}) or {}),
            publish=PublishConfig.from_dict(data.get("publish", {}) or {}),
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
