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

# Error markers we scan run logs for (the reality loop's evaluation). Kept broad so the same
# scan works across engines; the UE verify harness's PLAYSMITH_ASSERT lines are the primary,
# load-bearing signal (CLAUDE.md §4).
_ERROR_MARKERS = (
    "ERROR:",
    "Error:",
    "Fatal error",
    "Assertion failed",
    "Failed to load",
    "Can't open",
)

# Benign messages that match a marker above but are NOT game bugs: harmless shutdown leaks and
# headless/display/RHI driver chatter. These must not fail the `no_errors` check.
_BENIGN_MARKERS = (
    "leaked at exit",
    "resources still in use at exit",
    "X11 Display is not available",
    "Could not initialize the display server",
    "Couldn't initialize display server",
    "Vulkan",  # headless RHI/driver chatter, not a game bug
    "OpenGL",
)


class EngineError(Exception):
    """Base class for engine-adapter failures."""


class EngineNotFoundError(EngineError):
    """The engine binary (e.g. ``UnrealEditor-Cmd``) was not found or is not executable."""


class ExportTarget(StrEnum):
    """Export/target presets (engine-agnostic identifiers)."""

    WEB = "Web"
    LINUX = "Linux/X11"
    WINDOWS = "Windows Desktop"
    MACOS = "macOS"
    ANDROID = "Android"
    IOS = "iOS"


@dataclass
class SceneSpec:
    """A scene to write as text: a project-relative path plus the serialized scene content.

    Used by engines with text-based scenes. Binary-asset engines (Unreal: ``.umap``/``.uasset``)
    author scenes via the editor / UE Python API instead, and reject text writes.
    """

    path: str  # relative to project root
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
        """Real error lines from the run (excluding benign shutdown/headless noise)."""
        out: list[str] = []
        for line in self.logs.splitlines():
            if not any(marker in line for marker in _ERROR_MARKERS):
                continue
            if any(benign in line for benign in _BENIGN_MARKERS):
                continue
            out.append(line.strip())
        return out


# The in-engine verify harness prints lines like `PLAYSMITH_ASSERT player_on_floor=true`.
# This is the machine-readable half of the reality loop a text model can actually read,
# and it works headless (CLAUDE.md §4).
ASSERT_PREFIX = "PLAYSMITH_ASSERT "
_TRUTHY = frozenset({"true", "1", "yes", "ok", "pass"})

# The assertion keys the verify harness can evaluate. Skills must declare checks from this set;
# the marketplace validates installed skills against it (see playsmith/skills/registry.py).
# Unreal structural checks come from the UE Python verify harness; richer playability/quality
# gates (PIE metrics, rendered-screenshot scoring) are layered on by the director/critic loop.
KNOWN_ASSERTIONS = frozenset(
    {
        "no_errors",
        "level_loads",
        "player_start_exists",
        "floor_exists",
        "player_exists",
        "goal_exists",
        "obstacles_exist",
    }
)


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
    """A uniform way to drive an engine. Unreal Engine 5.x (more can be added behind this)."""

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
    def import_assets(self) -> RunResult: ...
    def verify(
        self, checks: list[str] | None = None, *, scene: str | None = None
    ) -> VerifyResult: ...
