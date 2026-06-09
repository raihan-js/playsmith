"""Tests for the Stage 3 director (dress a cloned template). No real Unreal Engine needed."""

from __future__ import annotations

from playsmith.engines.unreal import director
from playsmith.llm import ChatResponse, TaskType


class _FakeGateway:
    """Records the task it was called with and replays one canned response."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.tasks: list = []

    def chat(self, messages, tools=None, task=TaskType.GENERAL, **kwargs) -> ChatResponse:
        self.tasks.append(task)
        return ChatResponse(content=self.content, tool_calls=[], finish_reason="stop")


def test_default_dressing_is_valid_and_has_one_goal() -> None:
    d = director.default_dressing()
    assert d["placements"]
    assert sum(1 for p in d["placements"] if p["role"] == "goal") == 1
    assert all(p["kind"] in director.PALETTE for p in d["placements"])


def test_palette_paths_are_clone_local_assets() -> None:
    for kind, (kind_type, path) in director.PALETTE.items():
        assert kind_type in ("mesh", "bp")
        assert path.startswith("/Game/LevelPrototyping/"), kind


def test_sanitize_clamps_ranges_and_drops_unknown_kinds() -> None:
    spec = {
        "theme": "  volcano  ",
        "objective": "x" * 500,
        "sun": {"color": [9, -9, 0.5], "intensity": 999, "pitch": 999},
        "fog": 5.0,
        "placements": [
            {"kind": "cube", "x": 99999, "y": -99999, "z": 99999, "sx": 99, "role": "obstacle"},
            {"kind": "not_a_real_asset", "x": 0, "y": 0, "z": 0},  # dropped
            {"kind": "jump_pad", "x": 100, "y": 100, "z": 20, "role": "prop"},
        ],
    }
    out = director._sanitize(spec)
    assert out["theme"] == "volcano"
    assert len(out["objective"]) <= 140
    assert 0.0 <= out["sun"]["color"][0] <= 1.0 and 0.0 <= out["sun"]["color"][1] <= 1.0
    assert 1.0 <= out["sun"]["intensity"] <= 12.0
    assert -85.0 <= out["sun"]["pitch"] <= -5.0
    assert 0.0 <= out["fog"] <= 0.1
    kinds = [p["kind"] for p in out["placements"]]
    assert kinds == ["cube", "jump_pad"]  # unknown kind dropped, others kept
    cube = out["placements"][0]
    assert abs(cube["x"]) <= director._BOUND_XY and 0.0 <= cube["z"] <= director._BOUND_Z
    assert cube["sx"] <= 8.0


def test_plan_dressing_parses_llm_json_via_reasoning_route() -> None:
    gw = _FakeGateway(
        'sure!\n{"theme":"ruins","objective":"reach the target","placements":'
        '[{"kind":"ramp","x":500,"y":0,"z":0,"role":"platform"},'
        '{"kind":"target","x":2000,"y":0,"z":120,"role":"goal"}]}'
    )
    out = director.plan_dressing("a parkour ruins run", "third-person", gw)
    assert out["theme"] == "ruins"
    assert [p["kind"] for p in out["placements"]] == ["ramp", "target"]
    assert gw.tasks == [TaskType.REASONING]  # director reasoning routes to the frontier model


def test_plan_dressing_falls_back_on_garbage() -> None:
    out = director.plan_dressing("anything", "third-person", _FakeGateway("no json here"))
    # Same as the safe default, except the title is derived from the prompt.
    assert out["placements"] == director.default_dressing()["placements"]
    assert out["title"] == "Anything"


def test_ask_includes_hints_and_requests_a_title() -> None:
    q = director._ask("a parkour run", "third-person", {"vibe": "spooky", "difficulty": "hard"})
    assert "spooky" in q and "hard" in q and '"title"' in q


def test_sanitize_keeps_title() -> None:
    out = director._sanitize({"title": "  Neon Drift  ", "placements": []})
    assert out["title"] == "Neon Drift"


def test_plan_dressing_uses_llm_title_then_prompt_fallback() -> None:
    gw = _FakeGateway('{"title":"Sky Temple","placements":'
                      '[{"kind":"target","x":0,"y":0,"z":100,"role":"goal"}]}')
    assert director.plan_dressing("explore a temple", "third-person", gw)["title"] == "Sky Temple"
    # No title in the JSON -> fall back to a Title-Cased prompt, not the generic default.
    gw2 = _FakeGateway('{"placements":[{"kind":"target","x":0,"y":0,"z":100,"role":"goal"}]}')
    assert director.plan_dressing("haunted castle escape", "first-person", gw2)["title"] == (
        "Haunted Castle Escape"
    )


def test_theme_palette_matches_keywords() -> None:
    assert director._theme_palette("a FROZEN ice fortress")["name"] == "frozen fortress"
    assert director._theme_palette("cross the lava and magma")["name"] == "volcanic"
    assert director._theme_palette("a deep jungle temple")["name"] == "overgrown jungle"
    assert director._theme_palette("a plain little adventure")["name"] == (
        director._NEUTRAL_THEME["name"]
    )


def test_fallback_title_honors_title_label() -> None:
    prompt = "GAME TITLE: Ashenveil Chronicles: Shattered Bloodlines\nGENRE: fighting game"
    assert director.fallback_title(prompt) == "Ashenveil Chronicles: Shattered Bloodlines"
    assert director.fallback_title("a frozen castle adventure here") == "A Frozen Castle Adventure"


def test_theme_matching_is_word_boundary() -> None:
    # the Ashenveil bug: "choices"/"voice" must NOT match the frozen 'ice' keyword
    assert director._theme_palette("a game about player choices and your voice")["name"] == (
        director._NEUTRAL_THEME["name"]
    )
    # dark-fantasy: ashfall / void / bloodlines -> ashen void (prefix match: 'ash' hits 'ashfall')
    assert director._theme_palette(
        "the Ashfall void weapon scattered the six bloodlines"
    )["name"] == "ashen void"


def test_apply_theme_makes_a_frozen_prompt_icy() -> None:
    spec = director.apply_theme(director.default_dressing(), "a frozen ruined fortress")
    assert spec["theme"] == "frozen fortress"
    plat = spec["palette"]["platform"]
    assert plat[2] > plat[0]  # structure is blue-dominant (icy), not warm
    assert spec["character"]["tint"][2] > spec["character"]["tint"][0]  # pale-blue character
    assert spec["sun"]["color"][2] >= spec["sun"]["color"][0]  # cool light
    assert spec["palette"]["hazard"][0] > 0.8  # gameplay accents stay readable across themes


def test_plan_dressing_applies_theme_even_on_llm_fallback() -> None:
    # garbage LLM -> default dressing, but a frozen prompt still produces an icy palette + theme
    out = director.plan_dressing("a frozen glacier survival run", "third-person",
                                 _FakeGateway("no json here"))
    assert out["theme"] == "frozen fortress"
    assert out["palette"]["platform"][2] > out["palette"]["platform"][0]


def test_augment_adds_objects_variety_and_one_goal() -> None:
    out = director._augment(director.default_dressing(), size="large")
    assert len(out["placements"]) > len(director.default_dressing()["placements"])
    assert all(p["kind"] in director.PALETTE for p in out["placements"])
    assert sum(1 for p in out["placements"] if p["role"] == "goal") == 1
    z_levels = {round(p["z"] / 100) for p in out["placements"]}
    assert len(z_levels) >= 2  # verticality


def test_improve_dressing_uses_richer_llm_plan() -> None:
    from playsmith.engines.unreal.critic import Critique

    crit = Critique(score=40, passed=False, dimensions={}, feedback=["add more"], summary="s")
    base = {"title": "Keep Me", "placements": [
        {"kind": "cube", "x": 100, "y": 0, "z": 50, "role": "obstacle"}]}
    gw = _FakeGateway(
        '{"title":"New","placements":['
        '{"kind":"cube","x":100,"y":0,"z":50,"role":"obstacle"},'
        '{"kind":"ramp","x":600,"y":100,"z":0,"role":"platform"},'
        '{"kind":"target","x":2200,"y":0,"z":120,"role":"goal"}]}'
    )
    out = director.improve_dressing("a run", "third-person", gw, base, crit)
    assert len(out["placements"]) == 3
    assert out["title"] == "Keep Me"  # title preserved across iterations
    assert gw.tasks == [TaskType.REASONING]


def test_improve_dressing_augments_when_llm_not_richer() -> None:
    from playsmith.engines.unreal.critic import Critique

    crit = Critique(score=30, passed=False, dimensions={}, feedback=["sparse"], summary="s")
    base = director.default_dressing()
    out = director.improve_dressing("x", "third-person", _FakeGateway("no json"), base, crit)
    # LLM gave nothing usable -> deterministic augmentation makes it strictly richer.
    assert len(out["placements"]) > len(base["placements"])


def test_default_and_sanitize_carry_character() -> None:
    assert "character" in director.default_dressing()
    out = director._sanitize(
        {"character": {"prefer": "  Quinn  ", "tint": [9, -1, 0.5]}, "placements": []}
    )
    assert out["character"]["prefer"] == "Quinn"
    assert all(0.0 <= c <= 1.0 for c in out["character"]["tint"])


def test_character_script_discovers_assets_and_asserts() -> None:
    s = director.character_script(
        director.default_dressing(), "/Game/X/BP_Char", "/Game/Characters"
    )
    assert "list_assets" in s and "SkeletalMesh" in s  # discovers what actually ships (no bad refs)
    assert "/Game/Characters" in s and "/Game/X/BP_Char" in s
    assert "SubobjectDataSubsystem" in s  # reliable headless access to BP component templates
    assert "skeletal_mesh_asset" in s  # variant swap
    # persistent theme tint via a MaterialInstanceConstant (not a runtime-only dynamic material)
    assert "MaterialInstanceConstant" in s
    assert "set_material_instance_vector_parameter_value" in s
    assert "MaterialInstanceDynamic" not in s  # the old broken API is gone
    assert "PLAYSMITH_ASSERT character_customized" in s
    assert "save_asset" in s  # persists the change


def test_dress_level_script_is_additive_and_uses_real_assets() -> None:
    script = director.dress_level_script(director.default_dressing(), "/Game/ThirdPerson/Lvl_X")
    assert "load_level(MAP)" in script and "new_level" not in script  # additive, not a rebuild
    assert "/Game/ThirdPerson/Lvl_X" in script
    assert "spawn_actor_from_class" in script
    assert "load_blueprint_class" in script  # palette Blueprints (jump pad / target / door)
    assert "save_dirty_packages" in script  # persists spawned World Partition external actors
    assert "destroy_actor" in script and "PS_" in script  # idempotent: clears prior PS_ objects
    assert "get_actor_bounds" in script  # clears the template demo course (keeps the big floor)
    assert "set_material" in script and "ROLE_COLOR" in script  # role-coloured, themed objects
    assert "PLAYSMITH_ASSERT objects_placed" in script
