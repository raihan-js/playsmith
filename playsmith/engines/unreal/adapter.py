"""EXPERIMENTAL Unreal Engine 5.x adapter (power-user track).

Godot remains Playsmith's default, fully-tested engine. This adapter implements the SAME
:class:`~playsmith.engines.base.EngineAdapter` interface for Unreal via the Remote Control API
(HTTP, default port 30010) and the ``UnrealEditor-Cmd`` CLI for headless run/build. Unreal differs
fundamentally from Godot — maps/assets are binary (``.umap``/``.uasset``), not text — so some
authoring operations are limited and must go through the editor / Remote Control rather than file
writes. This is intentionally a thin, advanced track; it is never a dependency of the core.

The MCP server ecosystem (e.g. ``remiphilippe/mcp-unreal``, UE 5.7) changes monthly — pin a
version when you wire one in (docs/ARCHITECTURE.md "open risks").
"""

from __future__ import annotations

import json
import os
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

# Epic's Unreal EULA royalty terms (surfaced so users see the cost Godot never has).
_ROYALTY_THRESHOLD = 1_000_000.0
_ROYALTY_RATE = 0.05
_ROYALTY_RATE_EGS = 0.035


def royalty_estimate(
    gross_revenue: float, *, via_egs: bool = False, egs_exempt_revenue: float = 0.0
) -> dict:
    """Estimate Unreal royalties.

    Epic charges 5% of lifetime gross revenue **above the first $1M per product** (3.5% if you
    launch via the Epic Games Store "Launch Everywhere with Epic"); revenue earned ON the Epic
    Games Store is royalty-exempt. Godot has **no** royalties, ever.
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


class UnrealAdapter:
    """An EXPERIMENTAL :class:`EngineAdapter` for Unreal 5.x. Advanced track; Godot is default."""

    def __init__(
        self,
        project_dir: str | os.PathLike[str],
        *,
        editor_cmd: str = "UnrealEditor-Cmd",
        remote_host: str = "http://localhost:30010",
        client: httpx.Client | None = None,
    ) -> None:
        self.project_dir = Path(project_dir).expanduser().resolve()
        self.editor_cmd = editor_cmd
        self.remote = RemoteControlClient(remote_host, client=client)

    # -- project authoring -----------------------------------------------------
    def _uproject_path(self) -> Path:
        existing = sorted(self.project_dir.glob("*.uproject"))
        if existing:
            return existing[0]
        return self.project_dir / (self.project_dir.name + ".uproject")

    def create_project(self, name: str, main_scene: str | None = None) -> None:
        """Write a minimal ``.uproject`` (text JSON). Content modules need the editor/templates."""
        self.project_dir.mkdir(parents=True, exist_ok=True)
        uproject = {
            "FileVersion": 3,
            "EngineAssociation": "5.4",
            "Category": "",
            "Description": name,
            "Modules": [],
            "Plugins": [{"Name": "RemoteControl", "Enabled": True}],
        }
        if main_scene:
            uproject["DefaultMap"] = main_scene
        (self.project_dir / (name + ".uproject")).write_text(json.dumps(uproject, indent=2))

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
            "Unreal maps/assets are binary (.umap/.uasset). Build levels via the editor or the "
            "Remote Control API, not text writes. (Godot uses text scenes; Unreal does not.)"
        )

    def add_asset(self, src: str, dest: str) -> Path:
        target = (self.project_dir / dest).resolve()
        if self.project_dir not in target.parents and target != self.project_dir:
            raise EngineError(f"Refusing to write outside the project: {dest}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(Path(src).expanduser().read_bytes())
        return target

    # -- process driving -------------------------------------------------------
    def _invoke(self, args: list[str], *, timeout_s: int) -> RunResult:
        cmd = [self.editor_cmd, *args]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        except FileNotFoundError as exc:
            raise EngineNotFoundError(
                f"Unreal editor '{self.editor_cmd}' not found. Install UE 5.x and set the path. "
                "(The Unreal track is experimental; Godot is the default engine.)"
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
        """Limited verification: run headless and derive ``no_errors`` from the logs.

        Unreal has no PLAYSMITH_ASSERT harness (that is a Godot text-scene technique); gameplay
        assertions on the Unreal track would go through the Remote Control API / automation tests.
        """
        result = self.run(headless=True, timeout_s=60, scene=scene)
        assertions = parse_assert_lines(result.logs)
        if checks is None or "no_errors" in checks:
            assertions["no_errors"] = not result.error_lines()
        return VerifyResult(
            run=result, assertions=assertions or {"no_errors": not result.error_lines()}
        )
