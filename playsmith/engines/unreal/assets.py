"""Bring generated art *into* the Unreal project — import a texture and apply it in the level.

The art generator (``llm/imagegen.py``) saves PNGs into a project; this closes the loop by actually
importing one as a ``Texture2D``, building a simple material from it, and applying that material to
the level's ground meshes — so the generated art shows up in the playable game, not just on disk.

The UE Python here is **defensive** (every step in try/except) and uses the documented asset +
material APIs (AssetImportTask + TextureFactory, MaterialEditingLibrary). It writes
``texture_imported`` / ``material_applied`` via ``$PLAYSMITH_UE_OUT``. Like the rest of the engine
code it never raises — a failed apply just leaves the level as it was. Needs an on-machine UE run.
"""

from __future__ import annotations

import json

# Where imported textures/materials land inside the project's content.
DEST_PATH = "/Game/Playsmith/Textures"


def import_and_apply_script(
    png_path: str, map_path: str, dest_path: str = DEST_PATH
) -> str:
    """UE Python: import ``png_path`` as a Texture2D, build a material, apply it to the ground.

    Heuristic for "ground": large/flat StaticMeshActors in the loaded level (scale ≥ 5 on X or Y).
    Persists via save. Returns the script text (run it through the adapter's pythonscript path).
    """
    cfg = json.dumps({"png": png_path, "map": map_path, "dest": dest_path})
    return (
        "import json, os\n"
        "import unreal\n"
        f"CFG = json.loads(r'''{cfg}''')\n"
        'OUT = os.environ.get("PLAYSMITH_UE_OUT", "")\n'
        "imported = False\n"
        "applied = 0\n"
        "tex = None\n"
        "mat = None\n"
        "try:\n"
        "    task = unreal.AssetImportTask()\n"
        "    task.filename = CFG['png']\n"
        "    task.destination_path = CFG['dest']\n"
        "    task.automated = True\n"
        "    task.replace_existing = True\n"
        "    task.save = True\n"
        "    task.factory = unreal.TextureFactory()\n"
        "    tools = unreal.AssetToolsHelpers.get_asset_tools()\n"
        "    tools.import_asset_tasks([task])\n"
        "    paths = list(task.get_editor_property('imported_object_paths') or [])\n"
        "    tex = unreal.EditorAssetLibrary.load_asset(paths[0]) if paths else None\n"
        "    imported = tex is not None\n"
        "except Exception as e:\n"
        "    unreal.log_warning('PLAYSMITH texture import failed: %s' % e)\n"
        "try:\n"
        "    if tex is not None:\n"
        "        tools = unreal.AssetToolsHelpers.get_asset_tools()\n"
        "        mat = tools.create_asset('M_PS_Ground', CFG['dest'], "
        "unreal.Material, unreal.MaterialFactoryNew())\n"
        "        node = unreal.MaterialEditingLibrary.create_material_expression("
        "mat, unreal.MaterialExpressionTextureSample, -350, 0)\n"
        "        node.set_editor_property('texture', tex)\n"
        "        unreal.MaterialEditingLibrary.connect_material_property("
        "node, 'RGB', unreal.MaterialProperty.MP_BASE_COLOR)\n"
        "        unreal.MaterialEditingLibrary.recompile_material(mat)\n"
        "except Exception as e:\n"
        "    unreal.log_warning('PLAYSMITH material build failed: %s' % e)\n"
        "try:\n"
        "    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)\n"
        "    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)\n"
        "    les.load_level(CFG['map'])\n"
        "    if mat is not None:\n"
        "        for a in eas.get_all_level_actors():\n"
        "            if isinstance(a, unreal.StaticMeshActor):\n"
        "                s = a.get_actor_scale3d()\n"
        "                if s.x >= 5.0 or s.y >= 5.0:  # a large flat ground mesh\n"
        "                    a.static_mesh_component.set_material(0, mat)\n"
        "                    applied += 1\n"
        "    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)\n"
        "except Exception as e:\n"
        "    unreal.log_warning('PLAYSMITH texture apply failed: %s' % e)\n"
        "lines = [\n"
        "    'PLAYSMITH_ASSERT texture_imported=%s' % ('true' if imported else 'false'),\n"
        "    'PLAYSMITH_ASSERT material_applied=%s' % ('true' if applied > 0 else 'false'),\n"
        "]\n"
        "if OUT:\n"
        "    with open(OUT, 'w') as f:\n"
        "        f.write('\\n'.join(lines) + '\\n')\n"
    )
