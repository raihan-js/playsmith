"""Unreal Engine 5.x adapter — Playsmith's engine.

Implements the :class:`~playsmith.engines.base.EngineAdapter` interface for Unreal via the
``UnrealEditor-Cmd`` CLI (headless run/build + UE Python) and the Remote Control API
(HTTP, default port 30010). Maps and assets are binary (``.umap``/``.uasset``), not text, so
authoring goes through the editor / UE Python / Remote Control rather than file writes.

The editor-in-the-loop MCP ecosystem (e.g. ``remiphilippe/mcp-unreal``, UE 5.7) moves fast —
pin a version when you wire one in (docs/ARCHITECTURE.md "open risks").
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from playsmith.engines.base import (
    EngineError,
    EngineNotFoundError,
    ExportTarget,
    RunResult,
    SceneSpec,
    VerifyResult,
    parse_assert_lines,
)
from playsmith.engines.unreal import (
    assetpacks,
    assets,
    director,
    render,
    template_clone,
    templates,
)

# Epic's Unreal EULA royalty terms (surfaced so users can plan for the cost).
_ROYALTY_THRESHOLD = 1_000_000.0
_ROYALTY_RATE = 0.05
_ROYALTY_RATE_EGS = 0.035


def royalty_estimate(
    gross_revenue: float, *, via_egs: bool = False, egs_exempt_revenue: float = 0.0
) -> dict:
    """Estimate Unreal royalties.

    Epic charges 5% of lifetime gross revenue **above the first $1M per product** (3.5% if you
    launch via the Epic Games Store "Launch Everywhere with Epic"); revenue earned ON the Epic
    Games Store is royalty-exempt.
    """
    rate = _ROYALTY_RATE_EGS if via_egs else _ROYALTY_RATE
    royaltyable = max(0.0, (gross_revenue - max(0.0, egs_exempt_revenue)) - _ROYALTY_THRESHOLD)
    return {
        "gross_revenue": gross_revenue,
        "rate": rate,
        "threshold": _ROYALTY_THRESHOLD,
        "royaltyable_revenue": royaltyable,
        "royalty_owed": round(royaltyable * rate, 2),
        "via_egs": via_egs,
    }


class RemoteControlClient:
    """A thin client for Unreal's Remote Control HTTP API (default ``http://localhost:30010``)."""

    def __init__(
        self,
        host: str = "http://localhost:30010",
        *,
        client: httpx.Client | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.host = host.rstrip("/")
        self._client = client
        self._timeout = timeout

    def available(self) -> bool:
        try:
            resp = self._request("GET", "/remote/info")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def call(
        self,
        object_path: str,
        function_name: str,
        parameters: dict | None = None,
        *,
        timeout: float | None = None,
    ) -> dict:
        body = {
            "objectPath": object_path,
            "functionName": function_name,
            "parameters": parameters or {},
        }
        resp = self._request("PUT", "/remote/object/call", json=body, timeout=timeout)
        if resp.status_code >= 400:
            raise EngineError(
                f"Remote Control call failed (HTTP {resp.status_code}): {resp.text[:200]}"
            )
        try:
            return resp.json()
        except ValueError:
            return {}

    def execute_python(self, command: str, *, timeout: float | None = None) -> dict:
        """Run a Python command/string in the LIVE editor (the editor-in-the-loop primitive).

        Calls ``PythonScriptLibrary.ExecutePythonCommand`` over Remote Control, so authoring runs in
        a real editor with a render context (SceneCapture/MRQ work), reliable Blueprint editing, and
        correct World Partition persistence — none of which the headless commandlet does well. The
        call is synchronous: the command has fully run in-editor by the time it returns.
        """
        return self.call(
            "/Script/PythonScriptPlugin.Default__PythonScriptLibrary",
            "ExecutePythonCommand",
            {"PythonCommand": command},
            timeout=timeout,
        )

    def _request(
        self, method: str, path: str, *, timeout: float | None = None, **kwargs
    ) -> httpx.Response:
        url = self.host + path
        to = self._timeout if timeout is None else timeout
        if self._client is not None:
            return self._client.request(method, url, timeout=to, **kwargs)
        return httpx.request(method, url, timeout=to, **kwargs)


# Common install locations to auto-find UnrealEditor-Cmd when the config value isn't a real path.
_COMMON_UE_CMDS = (
    "~/UnrealEngine/Engine/Binaries/Linux/UnrealEditor-Cmd",
    "/opt/UnrealEngine/Engine/Binaries/Linux/UnrealEditor-Cmd",
    "~/UnrealEngine/Engine/Binaries/Mac/UnrealEditor-Cmd",
)


def _resolve_editor(editor_cmd: str) -> str:
    """Return a usable UnrealEditor-Cmd: the given path/name if real, else a known install."""
    given = Path(editor_cmd).expanduser()
    if given.exists() or shutil.which(editor_cmd):
        return str(given) if given.exists() else editor_cmd
    for candidate in _COMMON_UE_CMDS:
        path = Path(candidate).expanduser()
        if path.exists():
            return str(path)
    return editor_cmd  # leave as-is; _invoke raises a clear EngineNotFoundError if missing


def _first_png(directory: Path) -> Path | None:
    """The first PNG under ``directory`` (UE writes HighResShots into a platform subfolder)."""
    if not directory.exists():
        return None
    pngs = sorted(directory.rglob("*.png"))
    return pngs[0] if pngs else None


class UnrealAdapter:
    """A :class:`EngineAdapter` for Unreal 5.x: drives UnrealEditor-Cmd headless via UE Python."""

    def __init__(
        self,
        project_dir: str | os.PathLike[str],
        *,
        editor_cmd: str = "UnrealEditor-Cmd",
        remote_host: str = "http://localhost:30010",
        client: httpx.Client | None = None,
    ) -> None:
        self.project_dir = Path(project_dir).expanduser().resolve()
        self.editor_cmd = _resolve_editor(editor_cmd)
        self.remote = RemoteControlClient(remote_host, client=client)

    # -- project authoring -----------------------------------------------------
    def _uproject_path(self) -> Path:
        existing = sorted(self.project_dir.glob("*.uproject"))
        if existing:
            return existing[0]
        return self.project_dir / (self.project_dir.name + ".uproject")

    def create_project(self, name: str, main_scene: str | None = None) -> None:
        """Write a Blueprint-only ``.uproject`` (Python enabled) + boot config for the level.

        No C++ modules, so there's nothing to compile — the editor opens it directly. The actual
        playable level is built by :meth:`scaffold` via the UE Python API.
        """
        self.project_dir.mkdir(parents=True, exist_ok=True)
        proj_name = re.sub(r"[^A-Za-z0-9]", "", name) or "Game"
        (self.project_dir / (proj_name + ".uproject")).write_text(templates.uproject(name))
        config_dir = self.project_dir / "Config"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "DefaultEngine.ini").write_text(
            templates.default_engine_ini(main_scene or templates.MAP)
        )

    def scaffold(self, spec: dict | None = None) -> RunResult:
        """Build a lit, themed, playable level (floor + lights + obstacles + goal + pawn).

        ``spec`` (optional) is an LLM-authored level layout; without it a safe default is built.
        Legacy primitive scaffold; prefer :meth:`create_from_template` (build-on-template).
        """
        return self._run_python(templates.build_level_script(spec), timeout_s=600)

    def create_from_template(
        self, genre: str, *, project_name: str
    ) -> template_clone.TemplateSpec:
        """Clone a shipping UE template (+ its shared content) into this project (CLAUDE.md §0).

        This is the build-on-template foundation: the cloned project is already a playable, lit,
        animated game. Returns the :class:`~..template_clone.TemplateSpec` so callers know the map
        and character paths to verify/dress. Raises :class:`EngineNotFoundError` if no UE root.
        """
        ue_root = template_clone.find_ue_root(self.editor_cmd)
        if ue_root is None:
            raise EngineNotFoundError(
                "Unreal Engine root not found. Set engine.unreal.editor_cmd to your "
                "UnrealEditor-Cmd path (a source build's editor is at "
                "<UE>/Engine/Binaries/<Platform>/UnrealEditor-Cmd)."
            )
        self.project_dir.mkdir(parents=True, exist_ok=True)
        return template_clone.clone_template(
            genre, self.project_dir, ue_root=ue_root, project_name=project_name
        )

    def dress_from_spec(self, spec: dict, map_path: str) -> VerifyResult:
        """Apply a director dressing spec to the cloned template's level (Stage 3 'act' step).

        Adds the spec's gameplay objects + lighting ADDITIVELY to the real template level and saves
        it, then parses the harness's ``PLAYSMITH_ASSERT`` lines (level_loads, objects_placed,
        goal_exists, placed_count). The dressed level becomes what opens/plays in the project.
        """
        out_file = self.project_dir / "Saved" / "playsmith_assert.txt"
        if out_file.exists():
            out_file.unlink()
        result = self._author(director.dress_level_script(spec, map_path), out_file=out_file)
        assertions: dict[str, bool] = {}
        if out_file.exists():
            assertions = parse_assert_lines(out_file.read_text())
        return VerifyResult(run=result, assertions=assertions)

    def customize_character(
        self, spec: dict, tspec: template_clone.TemplateSpec
    ) -> VerifyResult:
        """Apply the dressing's ``character`` look to the template's player pawn (Stage B).

        Discovers the character meshes that actually ship in this clone and (best-effort) swaps the
        variant + applies a theme tint, then parses ``character_customized``/``character_tinted``.
        Never raises for a missing customization — the level is already playable without it.
        """
        out_file = self.project_dir / "Saved" / "playsmith_assert.txt"
        if out_file.exists():
            out_file.unlink()
        result = self._author(
            director.character_script(spec, tspec.character_bp, tspec.character_dir),
            out_file=out_file,
        )
        assertions: dict[str, bool] = {}
        if out_file.exists():
            assertions = parse_assert_lines(out_file.read_text())
        return VerifyResult(run=result, assertions=assertions)

    def apply_texture(
        self, png_path: str | os.PathLike[str], tspec: template_clone.TemplateSpec
    ) -> VerifyResult:
        """Import a generated PNG as a Texture2D, build a material, and apply it to the ground.

        Brings generated art into the actual playable level (Stage B #4). Parses
        ``texture_imported``/``material_applied``; best-effort — never breaks the project.
        """
        out_file = self.project_dir / "Saved" / "playsmith_assert.txt"
        if out_file.exists():
            out_file.unlink()
        result = self._author(
            assets.import_and_apply_script(str(png_path), tspec.map_path), out_file=out_file
        )
        assertions: dict[str, bool] = {}
        if out_file.exists():
            assertions = parse_assert_lines(out_file.read_text())
        return VerifyResult(run=result, assertions=assertions)

    def verify_template(self, spec: template_clone.TemplateSpec) -> VerifyResult:
        """Verify a cloned template is a real playable project (map loads, character resolved).

        Runs the clone harness headless and parses its ``PLAYSMITH_ASSERT`` lines — the build-on-
        template analog of :meth:`verify` (CLAUDE.md §4).
        """
        out_file = self.project_dir / "Saved" / "playsmith_assert.txt"
        if out_file.exists():
            out_file.unlink()
        result = self._author(template_clone.clone_verify_script(spec), out_file=out_file)
        assertions: dict[str, bool] = {}
        if out_file.exists():
            assertions = parse_assert_lines(out_file.read_text())
        return VerifyResult(run=result, assertions=assertions)

    def set_main_scene(self, res_path: str) -> None:
        path = self._uproject_path()
        if not path.exists():
            raise EngineError("No .uproject; call create_project first.")
        data = json.loads(path.read_text())
        data["DefaultMap"] = res_path
        path.write_text(json.dumps(data, indent=2))

    def write_script(self, rel_path: str, code: str) -> Path:
        """Write a source/automation script (e.g. a Python or C++ file) into the project."""
        target = (self.project_dir / rel_path).resolve()
        if self.project_dir not in target.parents and target != self.project_dir:
            raise EngineError(f"Refusing to write outside the project: {rel_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(code)
        return target

    def write_scene(self, scene: SceneSpec) -> Path:
        raise EngineError(
            "Unreal maps/assets are binary (.umap/.uasset). Build levels via the editor, the UE "
            "Python API, or the Remote Control API — not text writes."
        )

    def add_asset(self, src: str, dest: str) -> Path:
        target = (self.project_dir / dest).resolve()
        if self.project_dir not in target.parents and target != self.project_dir:
            raise EngineError(f"Refusing to write outside the project: {dest}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(Path(src).expanduser().read_bytes())
        return target

    # -- process driving -------------------------------------------------------
    _NOT_FOUND = (
        "Unreal editor '{cmd}' not found. Install UE 5.x and set the path. "
        "Set engine.unreal.editor_cmd to your UnrealEditor-Cmd path."
    )

    def _invoke(
        self,
        args: list[str],
        *,
        timeout_s: int,
        env: dict[str, str] | None = None,
        done_file: Path | None = None,
    ) -> RunResult:
        cmd = [self.editor_cmd, *args]
        run_env = {**os.environ, **(env or {})}
        if done_file is not None:
            return self._invoke_until_done(
                cmd, run_env, timeout_s=timeout_s, is_ready=done_file.exists
            )
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout_s, env=run_env
            )
        except FileNotFoundError as exc:
            raise EngineNotFoundError(self._NOT_FOUND.format(cmd=self.editor_cmd)) from exc
        except subprocess.TimeoutExpired as exc:
            return RunResult(
                command=cmd,
                returncode=None,
                stdout=(exc.stdout.decode() if isinstance(exc.stdout, bytes) else exc.stdout) or "",
                stderr=(exc.stderr.decode() if isinstance(exc.stderr, bytes) else exc.stderr) or "",
                timed_out=True,
            )
        return RunResult(
            command=cmd,
            returncode=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
        )

    def _invoke_until_done(
        self,
        cmd: list[str],
        run_env: dict[str, str],
        *,
        timeout_s: int,
        is_ready: Callable[[], bool],
    ) -> RunResult:
        """Run UE headless but stop as soon as ``is_ready()`` is true (the artifact has landed).

        UE source-build editors reliably do their work (write the harness's result file, save a
        screenshot) and then HANG on shutdown — so a plain blocking run burns the whole timeout.
        We poll for the expected artifact and terminate the editor once it appears.
        """
        saved = self.project_dir / "Saved"
        saved.mkdir(parents=True, exist_ok=True)
        out_log, err_log = saved / "_playsmith_stdout.log", saved / "_playsmith_stderr.log"
        try:
            so = open(out_log, "w")  # noqa: SIM115 - closed in finally
            se = open(err_log, "w")  # noqa: SIM115
        except OSError:
            so = se = None
        try:
            proc = subprocess.Popen(cmd, stdout=so, stderr=se, text=True, env=run_env)
        except FileNotFoundError as exc:
            for fh in (so, se):
                if fh:
                    fh.close()
            raise EngineNotFoundError(self._NOT_FOUND.format(cmd=self.editor_cmd)) from exc

        deadline = time.monotonic() + timeout_s
        early = timed_out = False
        try:
            while True:
                if proc.poll() is not None:
                    break  # exited on its own
                if is_ready():
                    early = True
                    time.sleep(1.0)  # let the editor finish flushing the artifact
                    break
                if time.monotonic() > deadline:
                    timed_out = True
                    break
                time.sleep(0.5)
            if proc.poll() is None:  # work is done (or timed out) — don't wait out the hang
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
        finally:
            for fh in (so, se):
                if fh:
                    fh.close()
        return RunResult(
            command=cmd,
            returncode=proc.returncode,
            stdout=out_log.read_text(errors="ignore") if out_log.exists() else "",
            stderr=err_log.read_text(errors="ignore") if err_log.exists() else "",
            timed_out=timed_out and not early,
        )

    def _run_python(
        self, script_text: str, *, timeout_s: int, out_file: Path | None = None
    ) -> RunResult:
        """Run a UE Python script headless via the ``pythonscript`` commandlet.

        Results come back through ``out_file`` (exposed to the script as ``$PLAYSMITH_UE_OUT``),
        because the commandlet does not reliably surface ``print()`` on stdout.
        """
        saved = self.project_dir / "Saved"
        saved.mkdir(parents=True, exist_ok=True)
        script_path = saved / "playsmith_run.py"
        script_path.write_text(script_text)
        args = [
            str(self._uproject_path()),
            "-run=pythonscript",
            f"-script={script_path}",
            "-unattended",
            "-nullrhi",
            "-nosound",
            "-nosplash",
            "-nopause",
            "-stdout",
            "-NoLogTimes",
            "-notrace",  # don't start the trace server (a common headless shutdown-hang cause)
            "-noxgecontroller",
        ]
        if out_file is not None:
            # Early-exit once the harness writes its result file (UE hangs on shutdown).
            return self._invoke(
                args,
                timeout_s=timeout_s,
                env={"PLAYSMITH_UE_OUT": str(out_file)},
                done_file=out_file,
            )
        return self._invoke(args, timeout_s=timeout_s, env=None)

    def live_available(self) -> bool:
        """True if a running editor with Remote Control is reachable (editor-in-the-loop is on)."""
        return self.remote.available()

    def discover_assets(self, roots: tuple[str, ...] = assetpacks.MEGASCANS_ROOTS) -> dict:
        """Discover installed Megascans/Fab assets via the live editor (Phase 1 real assets).

        Runs the discovery script in the running editor (it has the asset registry loaded) and reads
        back the categorised pack JSON. Returns ``{}`` with no editor or nothing installed —
        so dressing simply falls back to the builtin prototype pack.
        """
        if not self.remote.available():
            return {}
        out_json = self.project_dir / "Saved" / "playsmith_assets.json"
        if out_json.exists():
            out_json.unlink()
        af = self.project_dir / "Saved" / "playsmith_assert.txt"
        self._run_python_live(assetpacks.discover_script(str(out_json), tuple(roots)), out_file=af)
        if out_json.exists():
            try:
                return json.loads(out_json.read_text())
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _run_python_live(
        self, script_text: str, *, out_file: Path, timeout_s: int = 600
    ) -> RunResult:
        """Run an authoring script in the LIVE editor via Remote Control (editor-in-the-loop).

        The same script the commandlet would run, but executed inside a running editor — which has a
        real render context, edits Blueprints reliably, and persists World Partition correctly.
        Results still come back through ``out_file``; the call is synchronous so it's written on
        return. The editor isn't our process, so we inject ``PLAYSMITH_UE_OUT`` into its Python env.
        """
        saved = self.project_dir / "Saved"
        saved.mkdir(parents=True, exist_ok=True)
        script_path = saved / "playsmith_live.py"
        script_path.write_text(script_text)
        command = (
            "import os\n"
            f"os.environ['PLAYSMITH_UE_OUT'] = r'{out_file}'\n"
            f"exec(open(r'{script_path}').read())\n"
        )
        try:
            self.remote.execute_python(command, timeout=float(timeout_s))
        except EngineError as exc:
            return RunResult(command=["remote", "execute_python"], returncode=1, stderr=str(exc))
        return RunResult(command=["remote", "execute_python"], returncode=0, stdout=str(out_file))

    def _author(self, script_text: str, *, out_file: Path, timeout_s: int = 600) -> RunResult:
        """Run an authoring script in the live editor if one is up, else the headless commandlet.

        This is the seam that makes Playsmith editor-in-the-loop: when a UE editor with Remote
        Control is running, authoring (dress/character/textures/verify) goes through it — fast
        (no per-op boot), render-capable, and WP-correct — and otherwise falls back to headless.
        """
        if self.remote.available():
            return self._run_python_live(script_text, out_file=out_file, timeout_s=timeout_s)
        return self._run_python(script_text, timeout_s=timeout_s, out_file=out_file)

    def version(self) -> str:
        result = self._invoke(["-version"], timeout_s=30)
        return (
            (result.stdout or result.stderr or "Unreal Engine (version unknown)")
            .strip()
            .splitlines()[0]
        )

    def run(
        self, *, headless: bool = True, timeout_s: int = 60, scene: str | None = None
    ) -> RunResult:
        args = [str(self._uproject_path()), "-game", "-unattended", "-stdout"]
        args.append("-nullrhi" if headless else "-windowed")
        if scene:
            args.append(scene)
        return self._invoke(args, timeout_s=timeout_s)

    def screenshot(self, out_path: str, *, scene: str | None = None) -> RunResult:
        """Capture via Remote Control (HighResShot). Needs the editor up with Remote Control on."""
        out = Path(out_path).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.remote.call(
                "/Script/EngineSettings.Default__GameMapsSettings",
                "HighResShot",
                {"filename": str(out)},
            )
        except EngineError as exc:
            return RunResult(command=["remote", "HighResShot"], returncode=1, stderr=str(exc))
        return RunResult(command=["remote", "HighResShot"], returncode=0, stdout=str(out))

    def render_screenshot(
        self,
        out_path: str | os.PathLike[str],
        *,
        scene: str | None = None,
        width: int = 1280,
        height: int = 720,
        timeout_s: int = 600,
    ) -> RunResult:
        """Render a REAL frame of the level on the GPU, headless, and save it to ``out_path``.

        Editor-in-the-loop rendering (CLAUDE.md §0 Stage 2): boots UE in ``-game -RenderOffscreen``
        (Vulkan, no window/display) and captures a queued HighResShot, terminating the editor the
        moment the PNG lands. The FIRST render compiles the render shaders (slow — minutes — and
        the frame may show default materials); once the DDC is warm, renders are fast and clean.
        The captured PNG is copied to ``out_path`` (absent if nothing was captured). This is the
        rendered evidence the critic loop scores (Stage 3).
        """
        out = Path(out_path).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        shot_dir = self.project_dir / "Saved" / "Screenshots"
        shutil.rmtree(shot_dir, ignore_errors=True)
        args = [str(self._uproject_path())]
        if scene:
            args.append(scene)
        args += [
            "-game",
            "-RenderOffscreen",  # GPU render to an offscreen buffer — no display/window needed
            f"-ResX={width}",
            f"-ResY={height}",
            f"-ExecCmds=HighResShot {width}x{height}",
            "-unattended",
            "-nosound",
            "-nopause",
            "-nosplash",
            "-stdout",
            "-NoLogTimes",
            "-notrace",
            "-noxgecontroller",
        ]
        result = self._invoke_until_done(
            [self.editor_cmd, *args],
            {**os.environ},
            timeout_s=timeout_s,
            is_ready=lambda: _first_png(shot_dir) is not None,
        )
        png = _first_png(shot_dir)
        if png is not None:
            shutil.copyfile(png, out)
        return result

    def render_establishing(
        self,
        out_path: str | os.PathLike[str],
        tspec: template_clone.TemplateSpec,
        *,
        width: int = 1280,
        height: int = 720,
        timeout_s: int = 600,
    ) -> RunResult:
        """Render an elevated establishing shot of the whole level (not the player's spawn view).

        With a **live editor** (Remote Control up), renders via SceneCapture2D straight to a PNG — a
        real render context, so no camera/`-game`/cleanup dance. **Headless** falls back to: a
        auto-activating preview camera framed on the dressing → render the GPU `-game` frame (which
        captures it) → remove the camera (each step terminated only after its artifact lands). The
        PNG is at ``out_path`` (absent if nothing was captured).
        """
        out = Path(out_path).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out_file = self.project_dir / "Saved" / "playsmith_assert.txt"
        if out_file.exists():
            out_file.unlink()

        if self.remote.available():  # editor-in-the-loop: SceneCapture works in a real editor
            return self._run_python_live(
                render.scene_capture_script(tspec.map_path, str(out), width, height),
                out_file=out_file,
                timeout_s=timeout_s,
            )

        self._run_python(
            render.place_camera_script(tspec.map_path), timeout_s=timeout_s, out_file=out_file
        )
        result = self.render_screenshot(
            out, scene=tspec.map_path, width=width, height=height, timeout_s=timeout_s
        )
        if out_file.exists():
            out_file.unlink()
        self._run_python(
            render.cleanup_camera_script(tspec.map_path), timeout_s=timeout_s, out_file=out_file
        )
        return result

    def play(self, *, scene: str | None = None, width: int = 1280, height: int = 720) -> int:
        """Launch the game in a real window for interactive play (WASD + mouse); non-blocking.

        Runs ``-game`` windowed on the GPU (no ``-nullrhi``/``-RenderOffscreen``) so a window opens
        and you actually walk around the dressed level. Because play renders many frames, World
        Partition streams everything in and materials resolve — so you see the REAL result (unlike
        the single-frame preview). Detached: returns the PID immediately; the game runs until you
        close its window. Needs a graphical display (``$DISPLAY``).
        """
        args = [str(self._uproject_path())]
        if scene:
            args.append(scene)
        args += [
            "-game",
            "-windowed",
            f"-ResX={width}",
            f"-ResY={height}",
            "-nosplash",
            "-notrace",
            "-noxgecontroller",
        ]
        try:
            proc = subprocess.Popen(  # noqa: S603 - detached interactive game session
                [self.editor_cmd, *args],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,  # outlive the launching process (e.g. the web request)
                env={**os.environ},
            )
        except FileNotFoundError as exc:
            raise EngineNotFoundError(self._NOT_FOUND.format(cmd=self.editor_cmd)) from exc
        return proc.pid

    def import_assets(self) -> RunResult:
        """Unreal imports assets through the editor/Interchange pipeline, not a CLI flag."""
        return RunResult(command=["unreal", "import"], returncode=0)

    def export(self, target: ExportTarget, out_path: str, *, debug: bool = False) -> RunResult:
        """EXPERIMENTAL: headless cook. Full packaging uses RunUAT BuildCookRun (see UE docs)."""
        out = Path(out_path).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        args = [
            str(self._uproject_path()),
            "-run=cook",
            "-targetplatform=Windows",
            "-unattended",
            "-stdout",
        ]
        return self._invoke(args, timeout_s=600)

    def verify(self, checks: list[str] | None = None, *, scene: str | None = None) -> VerifyResult:
        """Run the UE Python verify harness headless; parse ``PLAYSMITH_ASSERT`` from the file.

        Structural, headless checks (level loads, a PlayerStart/floor/pawn exist) — the Unreal
        the in-engine assertion harness (CLAUDE.md §4). ``no_errors`` is only evaluated if asked
        for (UE startup logs are noisy); the structural assertions are the load-bearing signal.
        """
        out_file = self.project_dir / "Saved" / "playsmith_assert.txt"
        if out_file.exists():
            out_file.unlink()
        result = self._author(templates.verify_script(scene or templates.MAP), out_file=out_file)
        assertions: dict[str, bool] = {}
        if out_file.exists():
            assertions = parse_assert_lines(out_file.read_text())
        if checks is not None and "no_errors" in checks:
            assertions["no_errors"] = not result.error_lines()
        return VerifyResult(run=result, assertions=assertions)
