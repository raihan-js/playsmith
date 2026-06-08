"""Tests for the configuration loader."""

from __future__ import annotations

import pytest

from playsmith.config import Config, ConfigError, load_config, save_runtime_patch


def test_loads_example_config_by_default() -> None:
    # With no local config/playsmith.yaml, the loader falls back to the example file.
    cfg = load_config()
    assert isinstance(cfg, Config)
    assert cfg.llm.provider == "ollama"
    assert cfg.llm.base_url.endswith("/v1")
    assert cfg.llm.num_ctx >= 16384  # 4K default breaks agentic editing; example uses 16K.
    assert cfg.engine.default == "unreal"


def test_explicit_yaml_overrides(tmp_path) -> None:
    cfg_file = tmp_path / "custom.yaml"
    cfg_file.write_text(
        "workspace_dir: ~/games\n"
        "llm:\n"
        "  provider: lmstudio\n"
        "  base_url: http://localhost:1234/v1\n"
        "  model: my-model\n"
        "  num_ctx: 32768\n"
    )
    cfg = load_config(cfg_file)
    assert cfg.llm.provider == "lmstudio"
    assert cfg.llm.model == "my-model"
    assert cfg.llm.num_ctx == 32768
    # ~ is expanded to an absolute path.
    assert str(cfg.workspace_dir).startswith("/")
    assert "~" not in str(cfg.workspace_dir)


def test_env_var_expansion_in_api_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MY_KEY", "secret-123")
    cfg_file = tmp_path / "c.yaml"
    cfg_file.write_text("llm:\n  api_key: ${MY_KEY}\n")
    cfg = load_config(cfg_file)
    assert cfg.llm.api_key == "secret-123"


def test_missing_config_raises(tmp_path) -> None:
    with pytest.raises(ConfigError):
        load_config(tmp_path / "does-not-exist.yaml")


def test_non_mapping_root_raises(tmp_path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("- just\n- a\n- list\n")
    with pytest.raises(ConfigError):
        load_config(bad)


def test_runtime_override_merges_and_persists(tmp_path) -> None:
    base = tmp_path / "playsmith.yaml"
    base.write_text("llm:\n  provider: openai\n  model: gpt-4o\n  num_ctx: 16384\n")
    assert load_config(base).llm.model == "gpt-4o"

    out = save_runtime_patch({"llm": {"model": "gpt-4o-mini"}}, config_path=base)
    assert out == tmp_path / "playsmith.runtime.yaml"
    assert out.exists()

    cfg = load_config(base)
    assert cfg.llm.model == "gpt-4o-mini"  # overridden
    assert cfg.llm.provider == "openai"  # untouched, deep-merged

    # A second patch is merged, not clobbered.
    save_runtime_patch({"llm": {"api_key": "sk-xyz"}}, config_path=base)
    cfg2 = load_config(base)
    assert cfg2.llm.model == "gpt-4o-mini"
    assert cfg2.llm.api_key == "sk-xyz"
