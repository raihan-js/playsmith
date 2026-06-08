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
from playsmith.engines.unreal import templates

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

    def call(self, object_path: str, function_name: str, parameters: dict | None = None) -> dict:
        body = {
            "objectPath": object_path,
            "functionName": function_name,
            "parameters": parameters or {},
        }
        resp = self._request("PUT", "/remote/object/call", json=body)
        if resp.status_code >= 400:
            raise EngineError(
                f"Remote Control call failed (HTTP {resp.status_code}): {resp.text[:200]}"
            )
        try:
            return resp.json()
        except ValueError:
            return {}

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        url = self.host + path
        if self._client is not None:
            return self._client.request(method, url, timeout=self._timeout, **kwargs)
        return httpx.request(method, url, timeout=self._timeout, **kwargs)


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
        """
        return self._run_python(templates.build_level_script(spec), timeout_s=600)

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
    def _invoke(
        self, args: list[str], *, timeout_s: int, env: dict[str, str] | None = None
    ) -> RunResult:
        cmd = [self.editor_cmd, *args]
        run_env = {**os.environ, **(env or {})}
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout_s, env=run_env
            )
        except FileNotFoundError as exc:
            raise EngineNotFoundError(
                f"Unreal editor '{self.editor_cmd}' not found. Install UE 5.x and set the path. "
                "Set engine.unreal.editor_cmd to your UnrealEditor-Cmd path."
            ) from exc
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
        env = {"PLAYSMITH_UE_OUT": str(out_file)} if out_file is not None else None
        return self._invoke(args, timeout_s=timeout_s, env=env)

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
        result = self._run_python(
            templates.verify_script(scene or templates.MAP), timeout_s=600, out_file=out_file
        )
        assertions: dict[str, bool] = {}
        if out_file.exists():
            assertions = parse_assert_lines(out_file.read_text())
        if checks is not None and "no_errors" in checks:
            assertions["no_errors"] = not result.error_lines()
        return VerifyResult(run=result, assertions=assertions)
