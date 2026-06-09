"""Tests for Fab/Megascans asset packs + real-asset dressing. No editor, no network."""

from __future__ import annotations

import json
import types

from playsmith.engines.unreal import assetpacks, director
from playsmith.engines.unreal.adapter import UnrealAdapter


def test_categorize_buckets_by_keyword() -> None:
    assert assetpacks.categorize("Nordic_Wall_01") == "obstacle"
    assert assetpacks.categorize("Snow_Floor_Slab") == "platform"
    assert assetpacks.categorize("Ice_Crystal_Shard") == "collectible"
    assert assetpacks.categorize("Ancient_Shrine") == "goal"
    assert assetpacks.categorize("Pine_Tree_03") == "cover"
    assert assetpacks.categorize("Mystery_Thing") == "prop"  # default


def test_asset_pack_helpers() -> None:
    pack = assetpacks.AssetPack(
        name="P", theme="frozen", source="megascans",
        by_role={"obstacle": ["/Game/A", "/Game/B"], "prop": ["/Game/C"]},
        ground_material="/Game/MI_Snow",
    )
    assert pack.is_real is True
    assert pack.assets_for("obstacle") == ["/Game/A", "/Game/B"]
    assert pack.assets_for("goal") == ["/Game/C"]  # falls back to prop
    assert assetpacks.BUILTIN_PACK.is_real is False
    assert assetpacks.BUILTIN_PACK.assets_for("platform")  # builtin always has something


def test_load_manifest_packs(tmp_path) -> None:
    (tmp_path / "nordic.json").write_text(json.dumps({
        "name": "Nordic Ruins", "theme": "frozen", "source": "megascans",
        "by_role": {"obstacle": ["/Game/Megascans/Wall"], "goal": ["/Game/Megascans/Shrine"]},
        "ground_material": "/Game/Megascans/MI_Snow",
    }))
    (tmp_path / "broken.json").write_text("{ not json")
    packs = assetpacks.load_manifest_packs(tmp_path)
    assert len(packs) == 1 and packs[0].name == "Nordic Ruins" and packs[0].is_real
    assert packs[0].by_role["obstacle"] == ["/Game/Megascans/Wall"]


def test_resolve_pack_prefers_discovery_then_manifest_then_builtin(tmp_path) -> None:
    manifest = assetpacks.AssetPack(
        name="M", theme="frozen", source="manifest", by_role={"obstacle": ["/Game/M/Wall"]}
    )
    # discovery wins
    disc = {"by_role": {"obstacle": ["/Game/Disc/Rock"]}, "ground_material": None}
    assert assetpacks.resolve_pack("frozen", discovered=disc, manifests=[manifest]).source == \
        "megascans"
    # no discovery -> matching manifest
    got = assetpacks.resolve_pack("a frozen fortress", discovered={}, manifests=[manifest])
    assert got.name == "M"
    # nothing -> builtin
    assert assetpacks.resolve_pack("x", discovered={}, manifests=[]).source == "builtin"


def test_apply_pack_binds_real_assets_and_skips_for_builtin() -> None:
    spec = {"placements": [
        {"kind": "cube", "x": 0, "y": 0, "z": 0, "role": "obstacle"},
        {"kind": "cube", "x": 1, "y": 0, "z": 0, "role": "goal"},
    ]}
    pack = assetpacks.AssetPack(
        name="P", theme="frozen", source="megascans",
        by_role={"obstacle": ["/Game/Rock1", "/Game/Rock2"], "goal": ["/Game/Shrine"]},
        ground_material="/Game/MI_Snow",
    )
    director.apply_pack(spec, pack)
    assert spec["placements"][0]["asset"] == "/Game/Rock1"
    assert spec["placements"][1]["asset"] == "/Game/Shrine"
    assert spec["tint_objects"] is False  # real assets keep their own materials
    assert spec["ground_material"] == "/Game/MI_Snow"


def test_dress_script_spawns_the_real_asset_and_skips_tint() -> None:
    spec = director.default_dressing()
    spec["placements"] = [{"kind": "cube", "x": 0, "y": 0, "z": 50, "role": "obstacle",
                           "asset": "/Game/Megascans/Nordic_Rock", "sx": 1, "sy": 1, "sz": 1}]
    spec["tint_objects"] = False
    spec["ground_material"] = "/Game/Megascans/MI_Snow"
    script = director.dress_level_script(spec, "/Game/X/Lvl")
    assert "/Game/Megascans/Nordic_Rock" in script  # the real mesh is placed
    assert "GROUND_MATERIAL" in script and "/Game/Megascans/MI_Snow" in script
    assert "p.get('asset')" in script  # the real-asset path branch exists


def test_discover_script_content() -> None:
    s = assetpacks.discover_script("/tmp/out.json", ("/Game/Megascans",))
    assert "get_asset_registry" in s and "list_assets" in s
    assert "/Game/Megascans" in s and "/tmp/out.json" in s
    assert "json.dump" in s


def test_adapter_discover_assets_without_editor_returns_empty(tmp_path) -> None:
    a = UnrealAdapter(tmp_path, editor_cmd="UnrealEditor-Cmd")
    a.remote = types.SimpleNamespace(available=lambda: False)
    assert a.discover_assets() == {}


def test_adapter_discover_assets_reads_editor_json(tmp_path, monkeypatch) -> None:
    a = UnrealAdapter(tmp_path, editor_cmd="UnrealEditor-Cmd")
    a.remote = types.SimpleNamespace(available=lambda: True)
    payload = {"source": "megascans", "by_role": {"obstacle": ["/Game/Megascans/Rock"]}}

    def fake_live(script, *, out_file, timeout_s=600):
        # the live editor would have written the assets JSON
        (tmp_path / "Saved").mkdir(parents=True, exist_ok=True)
        (tmp_path / "Saved" / "playsmith_assets.json").write_text(json.dumps(payload))

    monkeypatch.setattr(a, "_run_python_live", fake_live)
    assert a.discover_assets()["by_role"]["obstacle"] == ["/Game/Megascans/Rock"]
