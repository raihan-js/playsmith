"""Steam publishing via SteamPipe / ``steamcmd`` (Phase 3).

Guided and responsible (CLAUDE.md §8): we upload to a **non-default branch** by default and never
auto-promote to the live/default branch — promotion stays a deliberate human action in Steamworks.
``steamcmd`` is optional; a Steam partner account + a one-time ``steamcmd +login`` (Steam Guard)
are required to actually upload. Before upload we surface the AI-content disclosure.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from playsmith.engines import ExportTarget, GodotAdapter
from playsmith.engines.base import EngineAdapter
from playsmith.publish.base import PublishError, PublishResult
from playsmith.publish.compliance import steam_ai_disclosure


def build_app_vdf(app_id: str, depot_id: str, content_dir: Path, *, branch: str = "beta") -> str:
    """A minimal SteamPipe app-build VDF (set live branch empty so nothing auto-publishes)."""
    return (
        '"appbuild"\n'
        "{\n"
        f'\t"appid" "{app_id}"\n'
        '\t"desc" "Built with Playsmith"\n'
        '\t"buildoutput" "./output"\n'
        f'\t"contentroot" "{content_dir}"\n'
        f'\t"setlive" "{branch}"\n'
        '\t"depots"\n'
        "\t{\n"
        f'\t\t"{depot_id}"\n'
        "\t\t{\n"
        '\t\t\t"FileMapping"\n'
        "\t\t\t{\n"
        '\t\t\t\t"LocalPath" "*"\n'
        '\t\t\t\t"DepotPath" "."\n'
        '\t\t\t\t"recursive" "1"\n'
        "\t\t\t}\n"
        "\t\t}\n"
        "\t}\n"
        "}\n"
    )


class SteamPublisher:
    """A thin wrapper around ``steamcmd`` for SteamPipe uploads."""

    def __init__(self, steamcmd_path: str = "steamcmd", account: str = "") -> None:
        self.steamcmd_path = steamcmd_path
        self.account = account

    def available(self) -> bool:
        try:
            result = subprocess.run(
                [self.steamcmd_path, "+quit"], capture_output=True, text=True, timeout=60
            )
            return result.returncode == 0
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            return False

    def push(self, vdf_path: Path, *, account: str | None = None) -> PublishResult:
        login = account or self.account
        if not login:
            raise PublishError(
                "No Steam account configured. Set publish.steam.account and run "
                "`steamcmd +login <account>` once to satisfy Steam Guard."
            )
        cmd = [self.steamcmd_path, "+login", login, "+run_app_build", str(vdf_path), "+quit"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        except FileNotFoundError as exc:
            raise PublishError(f"steamcmd not found at '{self.steamcmd_path}'.") from exc
        return PublishResult(cmd, result.returncode, result.stdout or "", result.stderr or "")


def publish_steam(
    project_dir: str | Path,
    app_id: str,
    *,
    depot_id: str | None = None,
    branch: str = "beta",
    steamcmd_path: str = "steamcmd",
    account: str = "",
    godot_binary: str = "godot",
    adapter: EngineAdapter | None = None,
    publisher: SteamPublisher | None = None,
    console=None,
) -> PublishResult:
    """Export a desktop build and upload it to ``<app_id>`` on a non-default Steam branch."""
    if branch.lower() in ("default", "public"):
        raise PublishError(
            "Refusing to auto-publish to the default/live branch. Upload to a beta branch and "
            "promote it manually in Steamworks (responsible publishing — CLAUDE.md §8)."
        )
    adapter = adapter or GodotAdapter(project_dir, binary=godot_binary)
    publisher = publisher or SteamPublisher(steamcmd_path, account)

    if not publisher.available():
        raise PublishError(
            f"steamcmd not found at '{steamcmd_path}'. Install SteamPipe/steamcmd and set "
            "publish.steam.steamcmd_path."
        )

    content_dir = Path(adapter.project_dir) / "build" / "steam"
    exe = content_dir / "game.exe"
    export_result = adapter.export(ExportTarget.WINDOWS, str(exe))
    if not exe.exists():
        raise PublishError(
            f"Windows export did not produce {exe}. Install Godot's Windows export templates. "
            f"Logs: {export_result.logs[:300]}"
        )

    if console is not None:
        console.print(steam_ai_disclosure())  # generic; the user fills in specifics for their game

    depot = depot_id or str(int(app_id) + 1)  # Steam convention: first depot = appid + 1
    vdf_path = Path(adapter.project_dir) / "build" / f"app_build_{app_id}.vdf"
    vdf_path.write_text(build_app_vdf(app_id, depot, content_dir, branch=branch))

    result = publisher.push(vdf_path, account=account)
    if not result.ok:
        raise PublishError(f"steamcmd upload failed: {result.logs[:400]}")
    return result
