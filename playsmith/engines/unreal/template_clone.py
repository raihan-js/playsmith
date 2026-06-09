"""Build ON a shipping Unreal template instead of an empty scene (the #1 quality lever).

Every Playsmith game starts from one of UE's built-in templates — already a playable, lit,
animated game — which the director then dresses/tunes (CLAUDE.md §0). UE's template folder is
NOT self-contained: the playable map references shared content packs (the mannequin character,
level-prototyping meshes, input mappings) that the editor normally merges in *at project-creation
time*. So a naive folder copy yields an invisible character and an empty-looking level.

This module reproduces that merge headlessly:
  1. copy the template's ``Content/`` and ``Config/`` (minus the template-only ini files),
  2. for each ``SharedContentPacks`` the template declares, copy
     ``Templates/TemplateResources/<DetailLevel>/<MountName>/Content/*`` into the project's
     ``Content/<DestinationFilesFolder>/`` (the dest folder comes from the pack's manifest),
  3. write a Blueprint-only ``.uproject`` (template plugins + PythonScriptPlugin for the harness).

Verified against UE 5.7 on Linux. The shared Characters pack is ~126 MB, so a clone is a real
(large) UE project — that's the point.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

# Files the template ships that must NOT land in a generated project (UE's FilesToIgnore).
_TEMPLATE_ONLY_CONFIG = frozenset({"TemplateDefs.ini", "config.ini"})

_SHARED_PACK_RE = re.compile(
    r'SharedContentPacks=\(MountName="(?P<mount>[^"]+)"\s*,\s*DetailLevels=\("(?P<level>[^"]+)"\)'
)
_DEST_FOLDER_RE = re.compile(r'"DestinationFilesFolder"\s*:\s*"([^"]+)"')


@dataclass(frozen=True)
class TemplateSpec:
    """A built-in UE template Playsmith can clone, keyed by Playsmith genre."""

    genre: str
    template_dir: str  # under <UE>/Templates, e.g. "TP_ThirdPersonBP"
    map_path: str  # the playable level, e.g. "/Game/ThirdPerson/Lvl_ThirdPerson"
    character_bp: str  # the player character Blueprint asset
    character_dir: str = "/Game/Characters"  # shared-pack dir that must be present after clone


# The three genres, each mapped to a built-in UE template (CLAUDE.md §2). Third-person first.
TEMPLATES: dict[str, TemplateSpec] = {
    "third-person": TemplateSpec(
        "third-person",
        "TP_ThirdPersonBP",
        "/Game/ThirdPerson/Lvl_ThirdPerson",
        "/Game/ThirdPerson/Blueprints/BP_ThirdPersonCharacter",
    ),
    "first-person": TemplateSpec(
        "first-person",
        "TP_FirstPersonBP",
        "/Game/FirstPerson/Lvl_FirstPerson",
        "/Game/FirstPerson/Blueprints/BP_FirstPersonCharacter",
    ),
    "top-down": TemplateSpec(
        "top-down",
        "TP_TopDownBP",
        "/Game/TopDown/Lvl_TopDown",
        "/Game/TopDown/Blueprints/BP_TopDownCharacter",
    ),
}

# Where to look for a UE root when the editor path doesn't reveal one.
_COMMON_UE_ROOTS = (
    "~/UnrealEngine",
    "/opt/UnrealEngine",
    "/opt/unreal-engine",
)


class TemplateError(Exception):
    """Raised when a template or its shared content can't be located."""


# Next-gen rendering defaults (Phase 1 of NEXTGEN_ROADMAP): Lumen GI + reflections, Virtual Shadow
# Maps, TSR, mesh distance fields, real-time sky reflections, sensible post defaults. Software Lumen
# (no forced hardware ray tracing) so it works on a broad range of GPUs; the look comes from these +
# real assets. These are standard UE5 RendererSettings — safe to set explicitly, verifiable in the
# generated .ini. (Visual confirmation still needs an on-machine editor.)
_NEXTGEN_RENDER: dict[str, str] = {
    "r.DynamicGlobalIlluminationMethod": "1",  # Lumen
    "r.ReflectionMethod": "1",  # Lumen reflections
    "r.Shadow.Virtual.Enable": "1",  # Virtual Shadow Maps
    "r.AntiAliasingMethod": "4",  # Temporal Super Resolution
    "r.GenerateMeshDistanceFields": "True",  # required for software Lumen
    "r.SkyLight.RealTimeReflectionCapture": "1",
    "r.DefaultFeature.AutoExposure": "True",
    "r.DefaultFeature.Bloom": "True",
    "r.DefaultFeature.MotionBlur": "False",
}
_RENDER_MARKER = "; Playsmith next-gen rendering"


def ensure_render_settings(config_dir: Path) -> Path:
    """Ensure next-gen rendering settings in the project's ``DefaultEngine.ini`` (idempotent).

    Appends a Playsmith-managed ``[/Script/Engine.RendererSettings]`` block (Lumen, VSM, TSR, mesh
    distance fields, auto-exposure) once — UE merges duplicate section headers, so this layers over
    the template's own settings without parsing them. Returns the ini path.
    """
    config_dir = Path(config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)
    ini = config_dir / "DefaultEngine.ini"
    text = ini.read_text(errors="ignore") if ini.exists() else ""
    if _RENDER_MARKER in text:
        return ini
    lines = ["", _RENDER_MARKER + " (Lumen / VSM / TSR — software Lumen for broad GPU support)",
             "[/Script/Engine.RendererSettings]"]
    lines += [f"{key}={value}" for key, value in _NEXTGEN_RENDER.items()]
    ini.write_text((text.rstrip() + "\n" if text.strip() else "") + "\n".join(lines) + "\n")
    return ini


def find_ue_root(editor_cmd: str | None = None) -> Path | None:
    """Resolve the Unreal Engine root from the editor binary path, else common locations.

    A source build's editor lives at ``<UE>/Engine/Binaries/<Platform>/UnrealEditor-Cmd``, so the
    root is four parents up. If ``editor_cmd`` is just a name on ``$PATH`` we can't derive it, so
    fall back to known install dirs.
    """
    if editor_cmd:
        p = Path(editor_cmd).expanduser()
        if p.exists() and len(p.parents) >= 4 and (p.parents[3] / "Templates").is_dir():
            return p.parents[3]
    for candidate in _COMMON_UE_ROOTS:
        root = Path(candidate).expanduser()
        if (root / "Templates").is_dir():
            return root
    return None


def _parse_shared_packs(template_defs: str) -> list[tuple[str, str]]:
    """Return [(mount_name, detail_level), ...] declared in a template's ``TemplateDefs.ini``."""
    return [(m.group("mount"), m.group("level")) for m in _SHARED_PACK_RE.finditer(template_defs)]


def _dest_folder(pack_dir: Path, mount: str) -> str:
    """The ``Content/`` subfolder a shared pack lands in (manifest DestinationFilesFolder)."""
    manifest = pack_dir / "FeaturePack" / "manifest.json"
    if manifest.is_file():
        match = _DEST_FOLDER_RE.search(manifest.read_text(errors="ignore"))
        if match:
            return match.group(1)
    return mount


def _uproject_text(template_uproject: Path, name: str) -> str:
    """Blueprint-only ``.uproject``: the template's plugins + PythonScriptPlugin for the harness."""
    data: dict = {}
    if template_uproject.is_file():
        try:
            data = json.loads(template_uproject.read_text())
        except (json.JSONDecodeError, OSError):
            data = {}
    plugins = list(data.get("Plugins", []))
    # PythonScriptPlugin for the harness; RemoteControl(+Web) so a running editor can be driven
    # editor-in-the-loop (reliable authoring/render vs headless commandlets — roadmap Phase 0).
    for needed in ("PythonScriptPlugin", "RemoteControl", "RemoteControlWebInterface"):
        if not any(p.get("Name") == needed for p in plugins):
            plugins.append({"Name": needed, "Enabled": True})
    return json.dumps(
        {
            "FileVersion": 3,
            "EngineAssociation": "",
            "Category": "",
            "Description": name,
            "Modules": [],  # Blueprint-only: nothing to compile
            "Plugins": plugins,
        },
        indent=2,
    )


def clone_template(
    genre: str,
    dest_dir: Path,
    *,
    ue_root: Path,
    project_name: str,
) -> TemplateSpec:
    """Clone a built-in UE template (+ its shared content packs) into ``dest_dir``.

    Returns the :class:`TemplateSpec` (so callers know the map/character paths to verify). Raises
    :class:`TemplateError` if the genre is unknown or the template/shared content is missing.
    """
    spec = TEMPLATES.get(genre)
    if spec is None:
        raise TemplateError(
            f"Unknown genre '{genre}'. Known: {', '.join(sorted(TEMPLATES))}."
        )
    template_root = ue_root / "Templates" / spec.template_dir
    if not template_root.is_dir():
        raise TemplateError(f"Template not found: {template_root}")

    dest_dir = Path(dest_dir)
    dest_content = dest_dir / "Content"
    dest_config = dest_dir / "Config"

    # 1. The template's own Content (the map, blueprints, external actors).
    shutil.copytree(template_root / "Content", dest_content, dirs_exist_ok=True)

    # 2. Config, minus the template-only ini files (UE's FilesToIgnore).
    if (template_root / "Config").is_dir():
        shutil.copytree(template_root / "Config", dest_config, dirs_exist_ok=True)
        for ignored in _TEMPLATE_ONLY_CONFIG:
            (dest_config / ignored).unlink(missing_ok=True)
    ensure_render_settings(dest_config)  # next-gen rendering (Lumen / VSM / TSR) — see roadmap

    # 3. Shared content packs (mannequin, level-prototyping, input, cursor, ...) merged in by hand.
    defs = (template_root / "Config" / "TemplateDefs.ini").read_text(errors="ignore")
    resources = ue_root / "Templates" / "TemplateResources"
    for mount, level in _parse_shared_packs(defs):
        pack_dir = resources / level / mount
        pack_content = pack_dir / "Content"
        if not pack_content.is_dir():
            raise TemplateError(
                f"Shared content pack missing: {pack_content} (needed by {spec.template_dir})."
            )
        dest = dest_content / _dest_folder(pack_dir, mount)
        shutil.copytree(pack_content, dest, dirs_exist_ok=True)

    # 4. The project file.
    (dest_dir / f"{project_name}.uproject").write_text(
        _uproject_text(template_root / f"{spec.template_dir}.uproject", project_name)
    )
    return spec


def clone_verify_script(spec: TemplateSpec) -> str:
    """A UE Python harness that proves the CLONE is a real, playable project (PLAYSMITH_ASSERT).

    Checks: the template map loads; a PlayerStart exists; the level has geometry; and the player
    character Blueprint + its shared character content resolve (proving the shared packs were
    merged — the part a naive folder-copy gets wrong).
    """
    return (
        "import os\n"
        "import unreal\n"
        f'MAP = "{spec.map_path}"\n'
        f'CHAR_BP = "{spec.character_bp}"\n'
        f'CHAR_DIR = "{spec.character_dir}"\n'
        'OUT = os.environ.get("PLAYSMITH_UE_OUT", "")\n'
        "les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)\n"
        "eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)\n"
        "loaded = les.load_level(MAP)\n"
        "actors = eas.get_all_level_actors()\n"
        "n_ps = sum(1 for a in actors if isinstance(a, unreal.PlayerStart))\n"
        "n_mesh = sum(1 for a in actors if isinstance(a, unreal.StaticMeshActor))\n"
        "char_bp = unreal.EditorAssetLibrary.does_asset_exist(CHAR_BP)\n"
        "char_assets = unreal.EditorAssetLibrary.list_assets(CHAR_DIR, recursive=True)\n"
        "char_present = bool(char_bp and len(char_assets) > 0)\n"
        "lines = [\n"
        '    "PLAYSMITH_ASSERT level_loads=%s" % ("true" if loaded else "false"),\n'
        '    "PLAYSMITH_ASSERT player_start_exists=%s" % ("true" if n_ps > 0 else "false"),\n'
        '    "PLAYSMITH_ASSERT floor_exists=%s" % ("true" if n_mesh > 0 else "false"),\n'
        '    "PLAYSMITH_ASSERT character_present=%s" % ("true" if char_present else "false"),\n'
        "]\n"
        "if OUT:\n"
        '    with open(OUT, "w") as f:\n'
        '        f.write("\\n".join(lines) + "\\n")\n'
    )
