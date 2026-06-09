"""Establishing-shot preview rendering.

The default ``-game -RenderOffscreen`` render captures the *player* camera — which for a
first-person game is a useless eye-level spawn view, not the level. Headless alternatives that
*don't* work: a ``SceneCapture2D`` in a pythonscript commandlet produces no image (the commandlet
isn't a rendering context), and a ``BugItGo`` teleport crashes the ``-game`` process.

What does work: place an **auto-activating ``CameraActor``** in the level (a fast commandlet),
framed on the dressing's placed objects, so the working ``-game`` render captures *that* camera —
an elevated establishing shot of the whole level. A second commandlet removes it afterwards so play
is unaffected. The camera is labelled ``PS_PREVIEWCAM`` so cleanup is unambiguous.
"""

from __future__ import annotations

PREVIEW_CAM_LABEL = "PS_PREVIEWCAM"

# Shared head: load the map + subsystems + a result-logging helper (results via $PLAYSMITH_UE_OUT).
_HEAD = (
    "import os\n"
    "import unreal\n"
    'OUT = os.environ.get("PLAYSMITH_UE_OUT", "")\n'
    "def _write(lines):\n"
    "    if OUT:\n"
    "        with open(OUT, 'w') as f:\n"
    "            f.write('\\n'.join(lines) + '\\n')\n"
    "les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)\n"
    "eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)\n"
)


def place_camera_script(map_path: str, label: str = PREVIEW_CAM_LABEL) -> str:
    """UE Python: place an auto-activating establishing camera framed on the placed PS_ objects.

    Computes the centre + radius of the dressing (actors labelled ``PS_*``, excluding any prior
    preview cam) and positions an elevated camera looking down at it. Persists via save so the
    ``-game`` render can stream it in. Writes ``PLAYSMITH_ASSERT preview_cam=true|false``.
    """
    return (
        _HEAD + f'MAP = "{map_path}"\n'
        f'LABEL = "{label}"\n'
        "ok = False\n"
        "try:\n"
        "    les.load_level(MAP)\n"
        "    for a in list(eas.get_all_level_actors()):\n"
        "        try:\n"
        "            if a.get_actor_label() == LABEL:\n"
        "                eas.destroy_actor(a)\n"
        "        except Exception:\n"
        "            pass\n"
        "    pts = []\n"
        "    for a in eas.get_all_level_actors():\n"
        "        try:\n"
        "            if a.get_actor_label().startswith('PS_'):\n"
        "                pts.append(a.get_actor_location())\n"
        "        except Exception:\n"
        "            pass\n"
        "    if pts:\n"
        "        cx = sum(p.x for p in pts) / len(pts)\n"
        "        cy = sum(p.y for p in pts) / len(pts)\n"
        "        maxr = max((((p.x - cx) ** 2 + (p.y - cy) ** 2) ** 0.5) for p in pts)\n"
        "    else:\n"
        "        cx, cy, maxr = 1200.0, 0.0, 1800.0\n"
        "    maxr = max(maxr, 1500.0)\n"
        "    dist = max(2800.0, maxr * 2.3)\n"
        "    cam_loc = unreal.Vector(cx - dist * 0.7, cy - dist * 0.5, dist * 0.85)\n"
        "    tgt = unreal.Vector(cx, cy, 120.0)\n"
        "    rot = unreal.MathLibrary.find_look_at_rotation(cam_loc, tgt)\n"
        "    cam = eas.spawn_actor_from_class(unreal.CameraActor, cam_loc, rot)\n"
        "    cam.set_actor_label(LABEL)\n"
        "    _ap = 'auto_activate_for_player'\n"
        "    try:\n"
        "        cam.set_editor_property(_ap, unreal.AutoReceiveInput.PLAYER0)\n"
        "    except Exception:\n"
        "        cam.set_editor_property(_ap, 1)\n"
        "    try:\n"
        "        cam.camera_component.set_field_of_view(75.0)\n"
        "    except Exception:\n"
        "        pass\n"
        "    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)\n"
        "    ok = True\n"
        "except Exception as e:\n"
        "    unreal.log_warning('PLAYSMITH preview cam failed: %s' % e)\n"
        "_write(['PLAYSMITH_ASSERT preview_cam=%s' % ('true' if ok else 'false')])\n"
    )


def cleanup_camera_script(map_path: str, label: str = PREVIEW_CAM_LABEL) -> str:
    """UE Python: remove the preview camera so interactive play is unaffected."""
    return (
        _HEAD + f'MAP = "{map_path}"\n'
        f'LABEL = "{label}"\n'
        "removed = 0\n"
        "try:\n"
        "    les.load_level(MAP)\n"
        "    for a in list(eas.get_all_level_actors()):\n"
        "        try:\n"
        "            if a.get_actor_label() == LABEL:\n"
        "                eas.destroy_actor(a)\n"
        "                removed += 1\n"
        "        except Exception:\n"
        "            pass\n"
        "    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)\n"
        "except Exception as e:\n"
        "    unreal.log_warning('PLAYSMITH preview cam cleanup failed: %s' % e)\n"
        "_write(['PLAYSMITH_ASSERT preview_cam_removed=%d' % removed])\n"
    )
