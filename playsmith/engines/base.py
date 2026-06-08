"""The engine abstraction.

Nothing outside ``playsmith/engines/<engine>/`` should know engine specifics
(docs/ARCHITECTURE.md §3). Skills and the agent loop talk only to this interface.

Note on the interface vs. ARCHITECTURE.md: the adapter is *bound to one project
directory* at construction, so ``run``/``screenshot``/``export`` take no path. This is a
small refinement of the protocol sketch in the architecture doc and keeps call sites clean.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable

# Godot error markers we scan run logs for (used by the reality loop's evaluation).
_ERROR_MARKERS = (
    "SCRIPT ERROR",
    "ERROR:",
    "USER ERROR",
    "Parse Error",
    "Parser Error",
    "Failed to load",
    "Can't open",
    'Condition "',
)


class EngineError(Exception):
    """Base class for engine-adapter failures."""


class EngineNotFoundError(EngineError):
    """The engine binary (e.g. ``godot``) was not found or is not executable."""


class ExportTarget(StrEnum):
    """Export presets. Values match the preset name Godot expects."""

    WEB = "Web"
    LINUX = "Linux/X11"
    WINDOWS = "Windows Desktop"
    MACOS = "macOS"


@dataclass
class SceneSpec:
    """A scene to write: a project-relative path plus the full ``.tscn`` text.

    Scenes are plain text in Godot 4, so the primary path is "hand the adapter the
    serialized ``.tscn``". Helpers in ``engines/godot/templates.py`` build common ones.
    """

    path: str  # relative to project root, e.g. "Player.tscn"
    content: str


@dataclass
class RunResult:
    """The outcome of running (or exporting) a project."""

    command: list[str]
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False

    @property
    def logs(self) -> str:
        """Combined stdout + stderr, the way the agent reads engine output."""
        parts = [p for p in (self.stdout, self.stderr) if p]
        return "\n".join(parts)

    @property
    def ok(self) -> bool:
        """True when the process exited cleanly and logged no engine errors."""
        return not self.timed_out and self.returncode == 0 and not self.error_lines()

    def error_lines(self) -> list[str]:
        """Lines in the logs that look like Godot parse/runtime errors."""
        out: list[str] = []
        for line in self.logs.splitlines():
            if any(marker in line for marker in _ERROR_MARKERS):
                out.append(line.strip())
        return out


# The in-engine verify harness prints lines like `PLAYSMITH_ASSERT player_on_floor=true`.
# This is the machine-readable half of the reality loop a text model can actually read,
# and it works headless (CLAUDE.md §4).
ASSERT_PREFIX = "PLAYSMITH_ASSERT "
_TRUTHY = frozenset({"true", "1", "yes", "ok", "pass"})


def parse_assert_lines(logs: str) -> dict[str, bool]:
    """Parse ``PLAYSMITH_ASSERT key=value`` lines emitted by the verify harness."""
    results: dict[str, bool] = {}
    for line in logs.splitlines():
        line = line.strip()
        if not line.startswith(ASSERT_PREFIX):
            continue
        body = line[len(ASSERT_PREFIX) :]
        if "=" in body:
            key, value = body.split("=", 1)
            results[key.strip()] = value.strip().lower() in _TRUTHY
    return results


@dataclass
class VerifyResult:
    """Per-check pass/fail from the assertion-based reality loop, plus the underlying run."""

    run: RunResult
    assertions: dict[str, bool] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """True only when there is at least one check and every check passed."""
        return bool(self.assertions) and all(self.assertions.values())

    def failures(self) -> list[str]:
        return [key for key, passed in self.assertions.items() if not passed]


@runtime_checkable
class EngineAdapter(Protocol):
    """A uniform way to drive any engine. Godot at MVP; Unreal in Phase 2."""

    project_dir: Path

    def version(self) -> str: ...
    def create_project(self, name: str, main_scene: str | None = None) -> None: ...
    def write_scene(self, scene: SceneSpec) -> Path: ...
    def write_script(self, rel_path: str, code: str) -> Path: ...
    def add_asset(self, src: str, dest: str) -> Path: ...
    def set_main_scene(self, res_path: str) -> None: ...
    def run(
        self, *, headless: bool = True, timeout_s: int = 30, scene: str | None = None
    ) -> RunResult: ...
    def screenshot(self, out_path: str, *, scene: str | None = None) -> RunResult: ...
    def export(self, target: ExportTarget, out_path: str, *, debug: bool = False) -> RunResult: ...
    def verify(
        self, checks: list[str] | None = None, *, scene: str | None = None
    ) -> VerifyResult: ...
