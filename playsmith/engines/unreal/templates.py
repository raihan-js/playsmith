"""UE 5.x Python automation: scaffold a lit, themed, playable level + verify it headless.

The Unreal analog of Godot's deterministic scaffold + ``PLAYSMITH_ASSERT`` harness. Scripts run via
``UnrealEditor-Cmd <proj> -run=pythonscript -script=<file>`` (the ``unreal`` module). Results come
back through a FILE (env ``PLAYSMITH_UE_OUT``) because the commandlet does not reliably surface
``print()``/``unreal.log()`` on stdout. Validated against UE 5.7 on Linux.

The level is parameterised by a *spec* (theme + lighting + obstacle layout + goal), so an LLM can
make every Unreal game different — see :mod:`playsmith.engines.unreal.level_director`.
"""

from __future__ import annotations

import json

MAP = "/Game/Maps/Main"


def default_spec() -> dict:
    """A safe, playable level when no LLM spec is available: a few obstacles and a goal."""
    return {
        "theme": "open sandbox",
        "sun": {"color": [1.0, 0.95, 0.85], "intensity": 6.0, "pitch": -45.0},
        "fog": 0.02,
        "obstacles": [
            {"x": 400, "y": 200, "z": 100, "sx": 2, "sy": 2, "sz": 2},
            {"x": 800, "y": -300, "z": 150, "sx": 3, "sy": 1, "sz": 3},
            {"x": 1200, "y": 100, "z": 100, "sx": 2, "sy": 2, "sz": 2},
        ],
        "goal": {"x": 1700, "y": 0, "z": 150},
        "player_start": {"x": -400, "y": 0, "z": 200},
    }


def uproject(name: str) -> str:
    """A minimal Blueprint-only ``.uproject`` (no C++ modules → no compile) with Python enabled."""
    return json.dumps(
        {
            "FileVersion": 3,
            "EngineAssociation": "",
            "Category": "",
            "Description": name,
            "Modules": [],
            "Plugins": [{"Name": "PythonScriptPlugin", "Enabled": True}],
        },
        indent=2,
    )


def default_engine_ini(map_path: str = MAP) -> str:
    """Boot the project straight into the generated level (editor + game default map)."""
    return (
        "[/Script/EngineSettings.GameMapsSettings]\n"
        f"GameDefaultMap={map_path}\n"
        f"EditorStartupMap={map_path}\n"
        f"ServerDefaultMap={map_path}\n"
    )


def build_level_script(spec: dict | None = None, map_path: str = MAP) -> str:
    """A UE Python script that builds a lit, themed, playable level from ``spec``.

    Ground plane + sky/sun/fog lighting + obstacle boxes (tagged ``obstacle``) + a goal sphere
    (tagged ``goal``) + a PlayerStart + a flyable DefaultPawn. Deterministic given the spec.
    """
    spec_json = json.dumps(spec or default_spec())
    return (
        "import json\n"
        "import unreal\n"
        f'MAP = "{map_path}"\n'
        f"SPEC = json.loads(r'''{spec_json}''')\n"
        "les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)\n"
        "eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)\n"
        "if unreal.EditorAssetLibrary.does_asset_exist(MAP):\n"
        "    unreal.EditorAssetLibrary.delete_asset(MAP)\n"  # idempotent re-scaffold
        "les.new_level(MAP)\n"
        'cube = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Cube")\n'
        'sphere = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Sphere")\n'
        "\n"
        "def box(x, y, z, sx, sy, sz, mesh, tag, label):\n"
        "    a = eas.spawn_actor_from_class("
        "unreal.StaticMeshActor, unreal.Vector(x, y, z), unreal.Rotator(0, 0, 0))\n"
        "    a.static_mesh_component.set_static_mesh(mesh)\n"
        "    a.set_actor_scale3d(unreal.Vector(sx, sy, sz))\n"
        "    a.set_actor_label(label)\n"
        "    if tag:\n"
        "        a.tags = [unreal.Name(tag)]\n"
        "    return a\n"
        "\n"
        '# Ground\nbox(0, 0, 0, 40, 40, 1, cube, "", "Floor")\n'
        "# Lighting: sun + sky + atmosphere + fog so it reads as a real 3D scene\n"
        'sun_pitch = float(SPEC.get("sun", {}).get("pitch", -45.0))\n'
        "sun = eas.spawn_actor_from_class("
        "unreal.DirectionalLight, unreal.Vector(0, 0, 1500), unreal.Rotator(sun_pitch, 0, 0))\n"
        "try:\n"
        '    sc = SPEC.get("sun", {})\n'
        '    sun.light_component.set_intensity(float(sc.get("intensity", 6.0)))\n'
        '    col = sc.get("color", [1.0, 0.95, 0.85])\n'
        "    sun.light_component.set_light_color("
        "unreal.Color(int(col[0]*255), int(col[1]*255), int(col[2]*255)))\n"
        "except Exception as e:\n"
        '    unreal.log_warning("PLAYSMITH sun tweak skipped: %s" % e)\n'
        "eas.spawn_actor_from_class("
        "unreal.SkyLight, unreal.Vector(0, 0, 800), unreal.Rotator(0, 0, 0))\n"
        "eas.spawn_actor_from_class("
        "unreal.SkyAtmosphere, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))\n"
        "eas.spawn_actor_from_class("
        "unreal.ExponentialHeightFog, unreal.Vector(0, 0, 200), unreal.Rotator(0, 0, 0))\n"
        "# Obstacles\n"
        'for o in SPEC.get("obstacles", []):\n'
        '    box(o["x"], o["y"], o["z"], o.get("sx", 2), o.get("sy", 2), o.get("sz", 2),'
        ' cube, "obstacle", "Obstacle")\n'
        "# Goal\n"
        'g = SPEC.get("goal", {"x": 1500, "y": 0, "z": 150})\n'
        'box(g["x"], g["y"], g["z"], 2, 2, 2, sphere, "goal", "Goal")\n'
        "# Player start + a flyable pawn\n"
        'p = SPEC.get("player_start", {"x": -400, "y": 0, "z": 200})\n'
        "ps = eas.spawn_actor_from_class("
        'unreal.PlayerStart, unreal.Vector(p["x"], p["y"], p["z"]), unreal.Rotator(0, 0, 0))\n'
        'ps.set_actor_label("PlayerStart")\n'
        "pawn = eas.spawn_actor_from_class("
        'unreal.DefaultPawn, unreal.Vector(p["x"], p["y"], p["z"] + 50), unreal.Rotator(0, 0, 0))\n'
        'pawn.set_actor_label("PlayerPawn")\n'
        "les.save_current_level()\n"
        'unreal.EditorAssetLibrary.save_directory("/Game/Maps")\n'
    )


def verify_script(map_path: str = MAP) -> str:
    """Load the level, count key actors (incl. goal/obstacle tags), write PLAYSMITH_ASSERT lines."""
    return (
        "import os\n"
        "import unreal\n"
        f'MAP = "{map_path}"\n'
        'OUT = os.environ.get("PLAYSMITH_UE_OUT", "")\n'
        "les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)\n"
        "eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)\n"
        "loaded = les.load_level(MAP)\n"
        "actors = eas.get_all_level_actors()\n"
        "n_ps = sum(1 for a in actors if isinstance(a, unreal.PlayerStart))\n"
        "n_mesh = sum(1 for a in actors if isinstance(a, unreal.StaticMeshActor))\n"
        "n_pawn = sum(1 for a in actors if isinstance(a, unreal.Pawn))\n"
        'n_goal = sum(1 for a in actors if a.actor_has_tag(unreal.Name("goal")))\n'
        'n_obs = sum(1 for a in actors if a.actor_has_tag(unreal.Name("obstacle")))\n'
        "lines = [\n"
        '    "PLAYSMITH_ASSERT level_loads=%s" % ("true" if loaded else "false"),\n'
        '    "PLAYSMITH_ASSERT player_start_exists=%s" % ("true" if n_ps > 0 else "false"),\n'
        '    "PLAYSMITH_ASSERT floor_exists=%s" % ("true" if n_mesh > 0 else "false"),\n'
        '    "PLAYSMITH_ASSERT player_exists=%s" % ("true" if n_pawn > 0 else "false"),\n'
        '    "PLAYSMITH_ASSERT goal_exists=%s" % ("true" if n_goal > 0 else "false"),\n'
        '    "PLAYSMITH_ASSERT obstacles_exist=%s" % ("true" if n_obs > 0 else "false"),\n'
        "]\n"
        "if OUT:\n"
        '    with open(OUT, "w") as f:\n'
        '        f.write("\\n".join(lines) + "\\n")\n'
    )
