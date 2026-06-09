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
# UI-managed settings (provider/model/API keys) are written here and deep-merged on top of the
# chosen base config at load time. Keeps the commented base file pristine and secrets out of it.
RUNTIME_OVERRIDE_NAME = "playsmith.runtime.yaml"

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


def _deep_merge(base: dict, over: dict) -> dict:
    """Recursively merge ``over`` onto ``base`` (over wins; nested dicts merged, not replaced)."""
    out = dict(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _expand(value: str) -> str:
    """Expand ``~`` and ``${ENV_VAR}`` references in a string value."""
    if not isinstance(value, str):
        return value

    def _sub(match: re.Match[str]) -> str:
        return os.environ.get(match.group(1), "")

    return os.path.expanduser(_ENV_PATTERN.sub(_sub, value))


def _load_dotenv() -> None:
    """Load ``KEY=VALUE`` pairs from a local ``.env`` into the environment (no external dep).

    Lets ``${VAR}`` references in the config resolve from a ``.env`` file (e.g. ``NVIDIA_API_KEY``,
    ``OPENAI_API_KEY``, ``ANTHROPIC_API_KEY``) without exporting them by hand. Real environment
    variables always win — existing values are never overwritten. The first ``.env`` found
    (current dir, then the repo root) is used.
    """
    for path in (Path.cwd() / ".env", REPO_ROOT / ".env"):
        if not path.is_file():
            continue
        try:
            for raw in path.read_text().splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                if key.startswith("export "):
                    key = key.split(None, 1)[1].strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
        except OSError:  # pragma: no cover - a bad .env must never break startup
            pass
        return  # first .env found wins


@dataclass
class LLMConfig:
    """A single LLM provider.

    Reached via the OpenAI-compatible ``/v1/chat/completions`` (``kind="openai"``, the default —
    covers Ollama, LM Studio, vLLM, OpenAI, OpenRouter, Gemini-compat) or Anthropic's native
    ``/v1/messages`` (``kind="anthropic"``). Playsmith is tiered: a frontier model (e.g. Claude
    via ``kind="anthropic"``) drives the director/critic; local models handle cheap sub-steps.
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
class UnrealConfig:
    # Path to UnrealEditor-Cmd (the headless editor binary). Full path or on $PATH.
    editor_cmd: str = "UnrealEditor-Cmd"

    @classmethod
    def from_dict(cls, data: dict) -> UnrealConfig:
        return cls(editor_cmd=_expand(data.get("editor_cmd", "UnrealEditor-Cmd")))


@dataclass
class EngineConfig:
    default: str = "unreal"
    unreal: UnrealConfig = field(default_factory=UnrealConfig)

    @classmethod
    def from_dict(cls, data: dict) -> EngineConfig:
        return cls(
            default=data.get("default", "unreal"),
            unreal=UnrealConfig.from_dict(data.get("unreal", {}) or {}),
        )


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
    _load_dotenv()  # so ${NVIDIA_API_KEY}/${OPENAI_API_KEY}/etc. resolve from a local .env
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
    overrides_path = config_path.parent / RUNTIME_OVERRIDE_NAME
    if overrides_path.exists():
        try:
            over = yaml.safe_load(overrides_path.read_text()) or {}
            if isinstance(over, dict):
                raw = _deep_merge(raw, over)
        except yaml.YAMLError:  # pragma: no cover - a broken override must not break startup
            pass
    return Config.from_dict(raw, source_path=config_path)


def save_runtime_patch(
    updates: dict, *, config_path: str | os.PathLike[str] | None = None
) -> Path:
    """Persist UI-managed settings to the runtime-overrides file next to the active config.

    Deep-merges ``updates`` into the existing overrides so unrelated settings are preserved.
    Returns the overrides file path. Values are stored literally (API keys are NOT ``${ENV}``
    references), so the next ``load_config`` picks them up everywhere.
    """
    base = _resolve_config_path(config_path)
    overrides_path = base.parent / RUNTIME_OVERRIDE_NAME
    existing: dict = {}
    if overrides_path.exists():
        try:
            loaded = yaml.safe_load(overrides_path.read_text()) or {}
            existing = loaded if isinstance(loaded, dict) else {}
        except yaml.YAMLError:
            existing = {}
    merged = _deep_merge(existing, updates)
    overrides_path.parent.mkdir(parents=True, exist_ok=True)
    overrides_path.write_text(yaml.safe_dump(merged, sort_keys=False))
    return overrides_path
