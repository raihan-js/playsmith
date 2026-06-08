"""Godot 4.x engine adapter — drives the ``godot`` CLI and writes text resources.

All file writes are confined to ``project_dir``; generated games live in the user's
workspace, never in this repo (CLAUDE.md §6). Skills/agents never shell out to ``godot``
directly — they go through this adapter (CLAUDE.md §6, docs/ARCHITECTURE.md §3).
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from playsmith.engines.base import (
    EngineError,
    EngineNotFoundError,
    ExportTarget,
    RunResult,
    SceneSpec,
    VerifyResult,
    parse_assert_lines,
)
from playsmith.engines.godot import templates

_MAIN_SCENE_RE = re.compile(r"^run/main_scene=.*$", re.MULTILINE)

# ExportTarget -> the platform string Godot expects in export_presets.cfg.
_EXPORT_PLATFORMS = {
    ExportTarget.WEB: "Web",
    ExportTarget.LINUX: "Linux/X11",
    ExportTarget.WINDOWS: "Windows Desktop",
    ExportTarget.MACOS: "macOS",
    ExportTarget.ANDROID: "Android",
    ExportTarget.IOS: "iOS",
}


class GodotAdapter:
    """An :class:`~playsmith.engines.base.EngineAdapter` for Godot 4.x.

    Bound to a single project directory. Construct one per generated game.
    """

    def __init__(self, project_dir: str | os.PathLike[str], *, binary: str = "godot") -> None:
        self.project_dir = Path(project_dir).expanduser().resolve()
        self.binary = binary

    # -- path safety -----------------------------------------------------------
    def _resolve_in_project(self, rel_path: str) -> Path:
        """Resolve a project-relative path, refusing anything that escapes project_dir."""
        rel = rel_path.replace("res://", "").lstrip("/")
        target = (self.project_dir / rel).resolve()
        if target != self.project_dir and self.project_dir not in target.parents:
            raise EngineError(f"Refusing to write outside the project: {rel_path}")
        return target

    @staticmethod
    def _write(path: Path, content: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    # -- project authoring -----------------------------------------------------
    def create_project(self, name: str, main_scene: str | None = None) -> None:
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self._write(
            self.project_dir / "project.godot",
            templates.project_godot(name, main_scene),
        )

    def set_main_scene(self, res_path: str) -> None:
        proj = self.project_dir / "project.godot"
        if not proj.exists():
            raise EngineError("No project.godot; call create_project first.")
        text = proj.read_text()
        line = f'run/main_scene="{res_path}"'
        if _MAIN_SCENE_RE.search(text):
            text = _MAIN_SCENE_RE.sub(line, text)
        elif "[application]" in text:
            text = text.replace("[application]\n", f"[application]\n\n{line}\n", 1)
        else:
            text = f"[application]\n{line}\n\n" + text
        proj.write_text(text)

    def write_scene(self, scene: SceneSpec) -> Path:
        return self._write(self._resolve_in_project(scene.path), scene.content)

    def write_script(self, rel_path: str, code: str) -> Path:
        return self._write(self._resolve_in_project(rel_path), code)

    def add_asset(self, src: str, dest: str) -> Path:
        target = self._resolve_in_project(dest)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(Path(src).expanduser().read_bytes())
        return target

    # -- process driving -------------------------------------------------------
    def _invoke(
        self, args: list[str], *, timeout_s: int, env: dict[str, str] | None = None
    ) -> RunResult:
        cmd = [self.binary, *args]
        run_env = {**os.environ, **(env or {})}
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                env=run_env,
            )
        except FileNotFoundError as exc:
            raise EngineNotFoundError(
                f"Godot binary '{self.binary}' not found. Install Godot 4.x and set "
                "engine.godot.binary in config/playsmith.yaml."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            return RunResult(
                command=cmd,
                returncode=None,
                stdout=exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
                stderr=exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or ""),
                timed_out=True,
            )
        return RunResult(
            command=cmd,
            returncode=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
        )

    def version(self) -> str:
        result = self._invoke(["--version"], timeout_s=15)
        if result.returncode not in (0, None):
            raise EngineError(f"`godot --version` failed: {result.logs}")
        return (result.stdout or result.stderr).strip()

    def run(
        self, *, headless: bool = True, timeout_s: int = 30, scene: str | None = None
    ) -> RunResult:
        """Run the project (or a specific scene), capturing logs and exit code.

        ``--quit-after`` makes the run finite so we can read the result; a generous
        frame count lets ``_ready`` and a few physics frames settle.
        """
        quit_after = max(30, min(timeout_s, 30) * 60)  # ~frames; cap so headless runs end
        args: list[str] = []
        if headless:
            args.append("--headless")
        args += ["--path", str(self.project_dir), "--quit-after", str(quit_after)]
        if scene:
            args.append(scene)
        return self._invoke(args, timeout_s=timeout_s)

    def screenshot(self, out_path: str, *, scene: str | None = None) -> RunResult:
        """Render a few frames and save a PNG.

        Needs a real display server (or ``xvfb-run`` on Linux); ``--headless`` produces a
        blank image because it uses the dummy renderer. We inject a tiny harness scene
        that instances the target scene, waits, captures the viewport, and quits.
        """
        out = Path(out_path).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        # Inject the harness (idempotent; safe to leave in the project).
        self.write_script(templates.SCREENSHOT_SCRIPT, templates.screenshot_harness_script())
        self.write_scene(
            SceneSpec(templates.SCREENSHOT_SCENE, templates.screenshot_harness_scene())
        )
        target = scene or self._current_main_scene() or ""
        env = {"PLAYSMITH_SCREENSHOT": str(out), "PLAYSMITH_TARGET_SCENE": target}
        args = [
            "--path",
            str(self.project_dir),
            "--quit-after",
            "30",
            f"res://{templates.SCREENSHOT_SCENE}",
        ]
        return self._invoke(args, timeout_s=30, env=env)

    def export(self, target: ExportTarget, out_path: str, *, debug: bool = False) -> RunResult:
        """Headless export to a build artifact (web HTML5, desktop, or mobile package)."""
        self._ensure_preset(target)
        out = Path(out_path).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        flag = "--export-debug" if debug else "--export-release"
        args = [
            "--headless",
            "--path",
            str(self.project_dir),
            flag,
            str(target.value),
            str(out),
        ]
        return self._invoke(args, timeout_s=600)

    def import_assets(self) -> RunResult:
        """Import project resources so newly-added files (e.g. generated PNGs) are usable.

        Game-mode runs (``--headless``) don't import; ``load("res://assets/foo.png")`` only works
        after the resource is imported. Run this after writing new assets into the project.
        """
        return self._invoke(
            ["--headless", "--import", "--path", str(self.project_dir)], timeout_s=180
        )

    def verify(self, checks: list[str] | None = None, *, scene: str | None = None) -> VerifyResult:
        """Run the assertion harness headless and report per-check pass/fail.

        Injects a probe scene that instances the target scene, lets physics settle, and prints
        ``PLAYSMITH_ASSERT`` lines. ``no_errors`` is derived from the run logs (parse/runtime
        errors), the rest from the harness. Unlike screenshots, this works headless.
        """
        self.write_script(templates.VERIFY_SCRIPT, templates.verify_harness_script())
        self.write_scene(SceneSpec(templates.VERIFY_SCENE, templates.verify_harness_scene()))
        target = scene or self._current_main_scene() or ""
        gameplay_checks = [c for c in (checks or []) if c != "no_errors"]
        env = {
            "PLAYSMITH_TARGET_SCENE": target,
            "PLAYSMITH_CHECKS": ",".join(gameplay_checks),
        }
        args = [
            "--headless",
            "--path",
            str(self.project_dir),
            "--quit-after",
            "300",
            f"res://{templates.VERIFY_SCENE}",
        ]
        result = self._invoke(args, timeout_s=60, env=env)
        assertions = parse_assert_lines(result.logs)
        if checks is None or "no_errors" in checks:
            assertions["no_errors"] = not result.error_lines()
        return VerifyResult(run=result, assertions=assertions)

    # -- helpers ---------------------------------------------------------------
    def _current_main_scene(self) -> str | None:
        proj = self.project_dir / "project.godot"
        if not proj.exists():
            return None
        match = _MAIN_SCENE_RE.search(proj.read_text())
        if not match:
            return None
        return match.group(0).split("=", 1)[1].strip().strip('"')

    def _ensure_preset(self, target: ExportTarget) -> None:
        """Append an export preset for ``target`` if the project doesn't already have one."""
        presets = self.project_dir / "export_presets.cfg"
        text = presets.read_text() if presets.exists() else ""
        if f'name="{target.value}"' in text:
            return
        indices = [int(m) for m in re.findall(r"\[preset\.(\d+)\]", text)]
        idx = (max(indices) + 1) if indices else 0
        block = templates.export_preset(
            idx, target.value, _EXPORT_PLATFORMS[target], web=(target is ExportTarget.WEB)
        )
        presets.write_text((text.rstrip() + "\n\n" + block) if text.strip() else block)
