"""Publish a generated game to itch.io via ``butler``.

Flow (docs/ARCHITECTURE.md §6): ensure a Web (HTML5) export exists, surface the AI-content /
compliance caveat, then ``butler push <build> <user>/<game>:<channel>``. ``butler`` is optional —
if it's missing we fail with a clear install hint, never a traceback.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from playsmith.engines import ExportTarget, GodotAdapter
from playsmith.engines.base import EngineAdapter


class PublishError(Exception):
    """A recoverable publishing failure (missing butler, failed export/push, bad target)."""


@dataclass
class PublishResult:
    command: list[str]
    returncode: int | None
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def logs(self) -> str:
        return "\n".join(p for p in (self.stdout, self.stderr) if p)


def itch_compliance_note() -> str:
    """The honest caveat we print before pushing (itch is lenient, but surface it)."""
    return (
        "[dim]Before you publish:\n"
        "  • itch.io is lenient, but if this game uses AI-generated player-facing art, consider\n"
        "    disclosing that on your itch page.\n"
        "  • Purely AI-generated assets have limited copyright protection (US Copyright Office).\n"
        "  • This publishes ONE game — never mass-submit near-identical games to stores.[/]"
    )


class ItchPublisher:
    """A thin wrapper around the itch.io ``butler`` CLI."""

    def __init__(self, butler_path: str = "butler") -> None:
        self.butler_path = butler_path

    def available(self) -> bool:
        try:
            result = subprocess.run(
                [self.butler_path, "version"], capture_output=True, text=True, timeout=15
            )
            return result.returncode == 0
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            return False

    def push(self, build_dir: Path, target: str, *, channel: str = "web") -> PublishResult:
        cmd = [self.butler_path, "push", str(build_dir), f"{target}:{channel}"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        except FileNotFoundError as exc:
            raise PublishError(
                f"butler not found at '{self.butler_path}'. Install it from itch.io/docs/butler."
            ) from exc
        return PublishResult(cmd, result.returncode, result.stdout or "", result.stderr or "")


def publish_itch(
    project_dir: str | Path,
    target: str,
    *,
    channel: str = "web",
    butler_path: str = "butler",
    godot_binary: str = "godot",
    adapter: EngineAdapter | None = None,
    publisher: ItchPublisher | None = None,
    console=None,
) -> PublishResult:
    """Export the project to HTML5 and push it to ``<target>:<channel>`` on itch.io."""
    if "/" not in target:
        raise PublishError(f"itch target must be 'user/game', got '{target}'.")
    adapter = adapter or GodotAdapter(project_dir, binary=godot_binary)
    publisher = publisher or ItchPublisher(butler_path)

    if not publisher.available():
        raise PublishError(
            f"butler not found at '{butler_path}'. Install it (itch.io/docs/butler) and set "
            "publish.itch.butler_path in config."
        )

    build_dir = Path(adapter.project_dir) / "build"
    index = build_dir / "index.html"
    export_result = adapter.export(ExportTarget.WEB, str(index))
    if not index.exists():
        raise PublishError(
            f"Web export did not produce {index}. Install Godot's HTML5 export templates. "
            f"Logs: {export_result.logs[:300]}"
        )

    if console is not None:
        console.print(itch_compliance_note())

    result = publisher.push(build_dir, target, channel=channel)
    if not result.ok:
        raise PublishError(f"butler push failed: {result.logs[:400]}")
    return result
