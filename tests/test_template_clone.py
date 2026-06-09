"""Tests for build-on-template cloning (filesystem-level; no real Unreal Engine needed)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from playsmith.engines.unreal import template_clone
from playsmith.engines.unreal.template_clone import TemplateError, TemplateSpec


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _fake_ue_root(tmp_path: Path) -> Path:
    """Build a minimal UE tree: one template that declares two shared content packs."""
    ue = tmp_path / "UE"
    tpl = ue / "Templates" / "TP_Fake"
    # Template's own content + a player-character blueprint + the playable map.
    _write(tpl / "Content" / "Fake" / "Lvl_Fake.umap", "umap")
    _write(tpl / "Content" / "Fake" / "Blueprints" / "BP_FakeCharacter.uasset", "bp")
    # Config: a real one to keep + two template-only files that must be dropped.
    _write(tpl / "Config" / "DefaultEngine.ini", "[URL]\nGameName=TP_Fake\n")
    _write(tpl / "Config" / "config.ini", "drop me")
    _write(
        tpl / "Config" / "TemplateDefs.ini",
        "[/Script/GameProjectGeneration.TemplateProjectDefs]\n"
        'SharedContentPacks=(MountName="LevelPrototyping",DetailLevels=("High"))\n'
        'SharedContentPacks=(MountName="Characters",DetailLevels=("High"))\n',
    )
    _write(tpl / "TP_Fake.uproject", json.dumps({"FileVersion": 3, "Plugins": [
        {"Name": "GameplayStateTree", "Enabled": True}]}))
    # Two shared content packs under TemplateResources/High, each with a manifest dest folder.
    res = ue / "Templates" / "TemplateResources" / "High"
    _write(res / "Characters" / "Content" / "Mannequins" / "SK_Mann.uasset", "mesh")
    _write(
        res / "Characters" / "FeaturePack" / "manifest.json",
        json.dumps({"AdditionalFiles": {"DestinationFilesFolder": "Characters"}}),
    )
    _write(res / "LevelPrototyping" / "Content" / "Meshes" / "SM_Cube.uasset", "mesh")
    _write(
        res / "LevelPrototyping" / "FeaturePack" / "manifest.json",
        json.dumps({"AdditionalFiles": {"DestinationFilesFolder": "LevelPrototyping"}}),
    )
    return ue


_FAKE_SPEC = TemplateSpec(
    "fake", "TP_Fake", "/Game/Fake/Lvl_Fake", "/Game/Fake/Blueprints/BP_FakeCharacter"
)


def test_parse_shared_packs() -> None:
    defs = (
        'SharedContentPacks=(MountName="LevelPrototyping",DetailLevels=("High"))\n'
        'SharedContentPacks=(MountName="Cursor",DetailLevels=("Standard"))\n'
    )
    assert template_clone._parse_shared_packs(defs) == [
        ("LevelPrototyping", "High"),
        ("Cursor", "Standard"),
    ]


def test_find_ue_root_from_editor_path(tmp_path) -> None:
    ue = _fake_ue_root(tmp_path)
    editor = ue / "Engine" / "Binaries" / "Linux" / "UnrealEditor-Cmd"
    editor.parent.mkdir(parents=True, exist_ok=True)
    editor.write_text("#!/bin/sh\n")
    assert template_clone.find_ue_root(str(editor)) == ue


def test_clone_merges_template_and_shared_packs(tmp_path, monkeypatch) -> None:
    ue = _fake_ue_root(tmp_path)
    monkeypatch.setitem(template_clone.TEMPLATES, "fake", _FAKE_SPEC)
    dest = tmp_path / "games" / "my-game"

    spec = template_clone.clone_template("fake", dest, ue_root=ue, project_name="MyGame")
    assert spec.map_path == "/Game/Fake/Lvl_Fake"

    # The template's own content (map + character BP) is present.
    assert (dest / "Content" / "Fake" / "Lvl_Fake.umap").is_file()
    assert (dest / "Content" / "Fake" / "Blueprints" / "BP_FakeCharacter.uasset").is_file()
    # The shared packs were merged into their manifest dest folders (the bit a naive copy misses).
    assert (dest / "Content" / "Characters" / "Mannequins" / "SK_Mann.uasset").is_file()
    assert (dest / "Content" / "LevelPrototyping" / "Meshes" / "SM_Cube.uasset").is_file()
    # Config kept, but the template-only ini files were dropped.
    assert (dest / "Config" / "DefaultEngine.ini").is_file()
    assert not (dest / "Config" / "TemplateDefs.ini").exists()
    assert not (dest / "Config" / "config.ini").exists()
    # A Blueprint-only .uproject with the Python plugin (for the verify harness) was written.
    proj = json.loads((dest / "MyGame.uproject").read_text())
    assert proj["Modules"] == []
    plugin_names = {p["Name"] for p in proj["Plugins"]}
    assert "PythonScriptPlugin" in plugin_names  # added for the harness
    assert "GameplayStateTree" in plugin_names  # preserved from the template


def test_clone_unknown_genre_raises(tmp_path) -> None:
    with pytest.raises(TemplateError, match="Unknown genre"):
        template_clone.clone_template("nope", tmp_path / "d", ue_root=tmp_path, project_name="X")


def test_clone_missing_shared_pack_raises(tmp_path, monkeypatch) -> None:
    ue = _fake_ue_root(tmp_path)
    # Remove a declared pack -> the clone must fail loudly, not produce a broken project.
    shutil.rmtree(ue / "Templates" / "TemplateResources" / "High" / "Characters")
    monkeypatch.setitem(template_clone.TEMPLATES, "fake", _FAKE_SPEC)
    with pytest.raises(TemplateError, match="Shared content pack missing"):
        template_clone.clone_template("fake", tmp_path / "g", ue_root=ue, project_name="MyGame")


def test_clone_verify_script_references_paths() -> None:
    script = template_clone.clone_verify_script(_FAKE_SPEC)
    assert "/Game/Fake/Lvl_Fake" in script
    assert "/Game/Fake/Blueprints/BP_FakeCharacter" in script
    assert "PLAYSMITH_ASSERT level_loads" in script
    assert "PLAYSMITH_ASSERT character_present" in script


def test_real_third_person_spec_registered() -> None:
    spec = template_clone.TEMPLATES["third-person"]
    assert spec.template_dir == "TP_ThirdPersonBP"
    assert spec.map_path == "/Game/ThirdPerson/Lvl_ThirdPerson"


def test_ensure_render_settings_writes_nextgen_block(tmp_path) -> None:
    ini = template_clone.ensure_render_settings(tmp_path)
    text = ini.read_text()
    assert "[/Script/Engine.RendererSettings]" in text
    assert "r.DynamicGlobalIlluminationMethod=1" in text  # Lumen GI
    assert "r.ReflectionMethod=1" in text  # Lumen reflections
    assert "r.Shadow.Virtual.Enable=1" in text  # Virtual Shadow Maps
    assert "r.AntiAliasingMethod=4" in text  # TSR


def test_ensure_render_settings_is_idempotent_and_preserves(tmp_path) -> None:
    ini = tmp_path / "DefaultEngine.ini"
    ini.write_text("[/Script/EngineSettings.GameMapsSettings]\nGameDefaultMap=/Game/X\n")
    template_clone.ensure_render_settings(tmp_path)
    first = ini.read_text()
    assert "GameDefaultMap=/Game/X" in first  # existing settings preserved
    assert "r.DynamicGlobalIlluminationMethod=1" in first  # nextgen added
    template_clone.ensure_render_settings(tmp_path)
    assert ini.read_text() == first  # not appended twice
