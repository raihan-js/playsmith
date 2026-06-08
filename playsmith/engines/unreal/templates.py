"""UE 5.x Python automation: scaffold a playable level + verify it headless.

The Unreal analog of Godot's text-scene scaffold + ``PLAYSMITH_ASSERT`` harness. These scripts run
via ``UnrealEditor-Cmd <proj> -run=pythonscript -script=<file>`` (the ``unreal`` module). Results
come back through a FILE (env ``PLAYSMITH_UE_OUT``) because ``print()``/``unreal.log()`` are not
reliably captured from the commandlet's stdout. Validated against UE 5.7 on Linux.
"""

from __future__ import annotations

import json

MAP = "/Game/Maps/Main"


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


def scaffold_level_script(map_path: str = MAP) -> str:
    """Build a deterministic playable level: a ground plane, a PlayerStart, and a default pawn."""
    return (
        "import unreal\n"
        f'MAP = "{map_path}"\n'
        "les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)\n"
        "eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)\n"
        "les.new_level(MAP)\n"
        'cube = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Cube")\n'
        "floor = eas.spawn_actor_from_class("
        "unreal.StaticMeshActor, unreal.Vector(0,0,0), unreal.Rotator(0,0,0))\n"
        'floor.set_actor_label("Floor")\n'
        "floor.static_mesh_component.set_static_mesh(cube)\n"
        "floor.set_actor_scale3d(unreal.Vector(40.0, 40.0, 1.0))\n"
        "ps = eas.spawn_actor_from_class("
        "unreal.PlayerStart, unreal.Vector(0,0,200), unreal.Rotator(0,0,0))\n"
        'ps.set_actor_label("PlayerStart")\n'
        "pawn = eas.spawn_actor_from_class("
        "unreal.DefaultPawn, unreal.Vector(0,0,260), unreal.Rotator(0,0,0))\n"
        'pawn.set_actor_label("PlayerPawn")\n'
        "les.save_current_level()\n"
        'unreal.EditorAssetLibrary.save_directory("/Game/Maps")\n'
    )


def verify_script(map_path: str = MAP) -> str:
    """Load the level, count key actors, write ``PLAYSMITH_ASSERT`` lines to the result file."""
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
        "lines = [\n"
        '    "PLAYSMITH_ASSERT level_loads=%s" % ("true" if loaded else "false"),\n'
        '    "PLAYSMITH_ASSERT player_start_exists=%s" % ("true" if n_ps > 0 else "false"),\n'
        '    "PLAYSMITH_ASSERT floor_exists=%s" % ("true" if n_mesh > 0 else "false"),\n'
        '    "PLAYSMITH_ASSERT player_exists=%s" % ("true" if n_pawn > 0 else "false"),\n'
        "]\n"
        "if OUT:\n"
        '    with open(OUT, "w") as f:\n'
        '        f.write("\\n".join(lines) + "\\n")\n'
    )
