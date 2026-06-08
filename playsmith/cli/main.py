"""Playsmith CLI entrypoint (Typer + Rich).

Command surface:
  version       — print version
  config-check  — show the resolved configuration (providers, routes, fallback)
  models        — route table + round-trip the default model (--eval for reliability)
  engine-check  — create + run a trivial Godot project headless
  skills        — list / search / install / remove game-generation skills (marketplace)
  new           — prompt -> scaffold -> generate -> assertion-verify
  edit          — apply a natural-language change to the latest project, then re-verify
  assets        — import <file> | generate "<prompt>" — 2D sprites or 3D meshes (optional)
  run           — run the latest generated project in a window
  export        — headless HTML5 export of the generated game
  publish       — publish to itch.io via butler (with a compliance reminder)
  unreal        — EXPERIMENTAL Unreal track (royalty calculator, availability check)
"""

from __future__ import annotations

import re
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from playsmith import __version__
from playsmith.assets import AssetError, ComfyUIClient, MeshClient
from playsmith.assets.mesh import MESH_CAVEAT
from playsmith.config import Config, ConfigError, load_config
from playsmith.engines import (
    EngineError,
    EngineNotFoundError,
    ExportTarget,
    GodotAdapter,
    SceneSpec,
)
from playsmith.engines.godot import templates as godot_templates
from playsmith.engines.unreal import UnrealAdapter, royalty_estimate
from playsmith.llm import LLMError, LLMGateway, Message
from playsmith.llm.eval import evaluate_targets
from playsmith.publish import PublishError, publish_itch, publish_steam
from playsmith.skills import SkillLoader, SkillRegistry, SkillRegistryError
from playsmith.studio import edit_game, latest_project, new_game

app = typer.Typer(
    name="playsmith",
    help="Turn a plain prompt into a real, editable, shippable game — locally.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


@app.command()
def version() -> None:
    """Print the Playsmith version."""
    console.print(f"Playsmith [bold cyan]{__version__}[/]")


@app.command(name="config-check")
def config_check(
    config: str = typer.Option(None, "--config", "-c", help="Path to a config YAML."),
) -> None:
    """Load the configuration and show how it resolves."""
    try:
        cfg: Config = load_config(config)
    except ConfigError as exc:
        console.print(f"[bold red]Config error:[/] {exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title="Playsmith configuration", show_header=True, header_style="bold")
    table.add_column("Setting", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")
    table.add_row("source", str(cfg.source_path or "<defaults>"))
    table.add_row("workspace_dir", str(cfg.workspace_dir))
    table.add_row("llm.provider", cfg.llm.provider)
    table.add_row("llm.base_url", cfg.llm.base_url)
    table.add_row("llm.model", cfg.llm.model)
    table.add_row("llm.num_ctx", str(cfg.llm.num_ctx))
    table.add_row("llm.kind", cfg.llm.kind)
    table.add_row("llm.api_key", "<set>" if cfg.llm.api_key else "<empty>")
    table.add_row("llm.routes", f"{len(cfg.llm_routes)} configured")
    table.add_row("llm.fallback", cfg.llm_fallback.model if cfg.llm_fallback else "<none>")
    table.add_row("engine.default", cfg.engine.default)
    table.add_row("engine.godot.binary", cfg.engine.godot.binary)
    table.add_row("assets.enabled", str(cfg.assets.enabled))
    console.print(table)


@app.command()
def models(
    config: str = typer.Option(None, "--config", "-c", help="Path to a config YAML."),
    prompt: str = typer.Option("Say hi in five words.", "--prompt", "-p", help="Message to send."),
    no_test: bool = typer.Option(
        False, "--no-test", help="Show the route table only; no round-trip."
    ),
    do_eval: bool = typer.Option(
        False, "--eval", help="Measure tool-call reliability per provider/route (router maturity)."
    ),
) -> None:
    """Show the configured providers/routes and round-trip a message to the default model.

    Proves the whole 'any model' foundation works: with Ollama running you get a real reply,
    and the table shows which provider each task type resolves to (router + cloud fallback).
    With --eval, measures how reliably each provider produces tool calls and recommends fallback.
    """
    try:
        cfg = load_config(config)
    except ConfigError as exc:
        console.print(f"[bold red]Config error:[/] {exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title="Configured models / routes", show_header=True, header_style="bold")
    for col in ("Route", "Provider", "Model", "Kind", "Endpoint", "Where"):
        table.add_column(col, style="cyan" if col == "Route" else None)

    def _row(label: str, lc) -> None:
        table.add_row(
            label, lc.provider, lc.model, lc.kind, lc.base_url, "local" if lc.is_local else "cloud"
        )

    _row("default", cfg.llm)
    for task, lc in cfg.llm_routes.items():
        _row(f"route:{task}", lc)
    if cfg.llm_fallback is not None:
        _row("fallback", cfg.llm_fallback)
    console.print(table)

    if do_eval:
        gateway = LLMGateway.from_config(cfg, console=console)
        targets = [("default", cfg.llm)]
        targets += [(f"route:{t}", lc) for t, lc in cfg.llm_routes.items()]
        if cfg.llm_fallback is not None:
            targets.append(("fallback", cfg.llm_fallback))
        etable = Table(title="Tool-call reliability (router maturity)", header_style="bold")
        for col in ("Target", "Model", "Reliability", "Meets 80%", "Recommendation"):
            etable.add_column(col)
        console.print("Running eval fixtures against each provider ...")
        for label, res in evaluate_targets(gateway, targets):
            etable.add_row(
                label,
                res.model,
                f"{res.reliability:.0%} ({res.successes}/{res.trials})",
                "[green]yes[/]" if res.meets_threshold else "[yellow]no[/]",
                res.recommendation,
            )
        console.print(etable)
        return

    if no_test:
        return

    gateway = LLMGateway.from_config(cfg, console=console)
    console.print(f"\nAsking [bold cyan]{cfg.llm.model}[/] at [dim]{cfg.llm.base_url}[/] ...")
    try:
        with console.status("waiting for the model..."):
            resp = gateway.chat([Message.user(prompt)])
    except LLMError as exc:
        console.print(f"[bold red]LLM error:[/] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[bold green]{cfg.llm.model}[/]: {resp.content or '<no content>'}")


@app.command(name="engine-check")
def engine_check(
    config: str = typer.Option(None, "--config", "-c", help="Path to a config YAML."),
) -> None:
    """Create a trivial Godot project in the workspace and run it headless.

    Proves Godot is wired up. The project it makes can be opened in the Godot editor.
    """
    try:
        cfg = load_config(config)
    except ConfigError as exc:
        console.print(f"[bold red]Config error:[/] {exc}")
        raise typer.Exit(code=1) from exc

    project_dir = cfg.workspace_dir.expanduser() / "_playsmith_engine_check"
    adapter = GodotAdapter(project_dir, binary=cfg.engine.godot.binary)

    try:
        ver = adapter.version()
    except (EngineNotFoundError, EngineError) as exc:
        console.print(f"[bold red]Engine error:[/] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"Found Godot: [bold cyan]{ver}[/]")

    adapter.create_project("Playsmith Engine Check", main_scene="res://Main.tscn")
    adapter.write_scene(SceneSpec("Main.tscn", godot_templates.trivial_main_scene()))
    console.print(f"Created trivial project at [dim]{project_dir}[/]")

    result = adapter.run(headless=True, timeout_s=30)
    if result.logs:
        console.print("[dim]--- engine logs ---[/]")
        console.print(result.logs)
    if result.ok:
        console.print("[bold green]engine-check passed[/] — Godot ran the project cleanly.")
    else:
        console.print("[bold red]engine-check failed[/] — see logs above.")
        for line in result.error_lines():
            console.print(f"  [red]{line}[/]")
        raise typer.Exit(code=1)


skills_app = typer.Typer(
    help="List / search / install / remove game-generation skills.", no_args_is_help=False
)
app.add_typer(skills_app, name="skills")


def _list_skills() -> None:
    found = SkillLoader().discover()
    if not found:
        console.print("[yellow]No skills found.[/]")
        return
    table = Table(title="Installed skills", show_header=True, header_style="bold")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Source")
    table.add_column("Description", style="white")
    for skill in found:
        if skill.source == "builtin":
            src = "builtin"
        elif skill.trusted:
            src = skill.source
        else:
            src = "[yellow]untrusted[/]"
        desc = skill.description
        table.add_row(skill.name, src, desc if len(desc) <= 70 else desc[:67] + "...")
    console.print(table)


def _registry(cfg: Config) -> SkillRegistry:
    return SkillRegistry(cfg.skills.registry_url, Path(cfg.skills.dir).expanduser())


@skills_app.callback(invoke_without_command=True)
def skills_main(ctx: typer.Context) -> None:
    """List installed skills when run with no subcommand."""
    if ctx.invoked_subcommand is None:
        _list_skills()


@skills_app.command("list")
def skills_list() -> None:
    """List installed game-generation skills (built-in + community)."""
    _list_skills()


@skills_app.command("search")
def skills_search(
    query: str = typer.Argument("", help="Search terms (blank = list all)."),
    config: str = typer.Option(None, "--config", "-c", help="Path to a config YAML."),
) -> None:
    """Search the community skill registry."""
    cfg = load_config(config)
    try:
        results = _registry(cfg).search(query)
    except SkillRegistryError as exc:
        console.print(f"[bold red]Registry error:[/] {exc}")
        raise typer.Exit(code=1) from exc
    if not results:
        console.print("[yellow]No matching skills in the registry.[/]")
        return
    table = Table(title="Registry skills", show_header=True, header_style="bold")
    for col in ("Name", "Version", "Author", "Trust", "Description"):
        table.add_column(col)
    for entry in results:
        trust = "trusted" if entry.trusted else "[yellow]untrusted[/]"
        table.add_row(entry.name, entry.version, entry.author, trust, entry.description[:55])
    console.print(table)


@skills_app.command("install")
def skills_install(
    name: str = typer.Argument(..., help="Skill name from the registry."),
    allow_untrusted: bool = typer.Option(
        False, "--allow-untrusted", help="Install even if the skill is from an untrusted source."
    ),
    config: str = typer.Option(None, "--config", "-c", help="Path to a config YAML."),
) -> None:
    """Install a community skill (verifies integrity; never runs its code)."""
    cfg = load_config(config)
    try:
        skill = _registry(cfg).install(name, allow_untrusted=allow_untrusted)
    except SkillRegistryError as exc:
        console.print(f"[bold red]Install refused:[/] {exc}")
        raise typer.Exit(code=1) from exc
    if skill.trusted:
        console.print(f"[bold green]Installed[/] {skill.name} (trusted) from {skill.source}")
    else:
        console.print(
            f"[bold yellow]Installed[/] {skill.name} [yellow](UNTRUSTED)[/] from {skill.source}. "
            "Review its scripts/diffs before playing games it makes."
        )


@skills_app.command("remove")
def skills_remove(
    name: str = typer.Argument(..., help="Installed community skill to remove."),
    config: str = typer.Option(None, "--config", "-c", help="Path to a config YAML."),
) -> None:
    """Remove an installed community skill (never touches built-in skills)."""
    cfg = load_config(config)
    if _registry(cfg).remove(name):
        console.print(f"[bold green]Removed[/] {name}")
    else:
        console.print(f"[yellow]Not an installed community skill:[/] {name}")
        raise typer.Exit(code=1)


assets_app = typer.Typer(help="Import or generate game art.", no_args_is_help=True)
app.add_typer(assets_app, name="assets")


@assets_app.command("import")
def assets_import(
    file: str = typer.Argument(..., help="Path to an image/audio file to import."),
    as_path: str = typer.Option(
        None, "--as", help="Destination res:// path (default assets/<name>)."
    ),
    project: str = typer.Option(None, "--project", "-p", help="Project dir (default: latest)."),
    config: str = typer.Option(None, "--config", "-c", help="Path to a config YAML."),
) -> None:
    """Copy an image/audio file into a generated project so the agent (and you) can use it."""
    cfg = load_config(config)
    src = Path(file).expanduser()
    if not src.is_file():
        console.print(f"[bold red]No such file:[/] {src}")
        raise typer.Exit(code=1)
    project_dir = _resolve_project(cfg, project)
    adapter = GodotAdapter(project_dir, binary=cfg.engine.godot.binary)
    dest = (as_path or f"assets/{src.name}").replace("res://", "")
    try:
        adapter.add_asset(str(src), dest)
    except (EngineError, OSError) as exc:
        console.print(f"[bold red]Import failed:[/] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(
        f"[bold green]Imported[/] {src.name} → res://{dest} in [bold]{project_dir.name}[/]"
    )
    console.print('Use it via a Sprite2D texture, or `playsmith edit "use the imported art"`.')


@assets_app.command("generate")
def assets_generate(
    prompt: str = typer.Argument(..., help="What art to generate, e.g. 'a pixel-art cat'."),
    kind: str = typer.Option("sprite", "--kind", "-k", help="sprite|portrait|background|mesh."),
    project: str = typer.Option(None, "--project", "-p", help="Project dir (default: latest)."),
    out: str = typer.Option(
        None, "--out", "-o", help="Output path (default <project>/assets/...)."
    ),
    config: str = typer.Option(None, "--config", "-c", help="Path to a config YAML."),
) -> None:
    """Generate a 2D sprite (ComfyUI) or a 3D mesh into a project (graceful if no backend)."""
    cfg = load_config(config)
    safe = re.sub(r"[^a-z0-9]+", "_", prompt.lower()).strip("_")[:40] or "asset"

    if kind.lower() in ("mesh", "3d", "model"):
        client = MeshClient(
            cfg.assets.mesh_url,
            backend=cfg.assets.mesh_backend,
            blender_path=cfg.assets.blender_path,
        )
        if not cfg.assets.mesh_url or not client.available():
            console.print(
                "[yellow]No 3D mesh backend reachable.[/] Games still ship with primitive meshes."
            )
            console.print(
                "[dim]Set assets.mesh_url to a Hunyuan3D/TRELLIS server to generate meshes.[/]"
            )
            raise typer.Exit(code=1)
        project_dir = _resolve_project(cfg, project)
        dest = Path(out).expanduser() if out else project_dir / "assets" / f"{safe}.glb"
        console.print(f"Generating a mesh for '{prompt}' via {cfg.assets.mesh_backend} ...")
        try:
            with console.status("rendering..."):
                client.mesh(prompt, str(dest))
        except (AssetError, OSError) as exc:
            console.print(f"[bold red]Generation failed:[/] {exc}")
            raise typer.Exit(code=1) from exc
        console.print(f"[bold green]Generated[/] {dest}")
        console.print(f"[yellow]{MESH_CAVEAT}[/]")
        return

    client = ComfyUIClient(cfg.assets.comfyui_url, model=cfg.assets.model)
    if not client.available():
        console.print(
            f"[yellow]ComfyUI not reachable at {cfg.assets.comfyui_url}.[/] "
            "Games still ship with placeholders."
        )
        console.print("[dim]Start ComfyUI and set assets.comfyui_url to generate real sprites.[/]")
        raise typer.Exit(code=1)
    project_dir = _resolve_project(cfg, project)
    dest = Path(out).expanduser() if out else project_dir / "assets" / f"{safe}.png"
    console.print(f"Generating [bold]{kind}[/] for '{prompt}' via ComfyUI ...")
    try:
        with console.status("rendering..."):
            client.image(prompt, kind, str(dest))
    except (AssetError, OSError) as exc:
        console.print(f"[bold red]Generation failed:[/] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"[bold green]Generated[/] {dest}")


def _resolve_project(cfg: Config, project: str | None) -> Path:
    """Resolve an explicit project path, or fall back to the most recent generated game."""
    if project:
        path = Path(project).expanduser()
        if not (path / "project.godot").exists():
            console.print(f"[bold red]No Godot project at[/] {path}")
            raise typer.Exit(code=1)
        return path
    found = latest_project(cfg.workspace_dir)
    if found is None:
        console.print(
            '[yellow]No generated project found.[/] Run `playsmith new "<prompt>"` first.'
        )
        raise typer.Exit(code=1)
    return found


def _print_build_outcome(outcome) -> None:
    """Shared result reporting for `new` and `edit`."""
    console.print()
    if outcome.runs_clean:
        console.print("[bold green]✓ The game runs and all gameplay checks pass.[/]")
    elif outcome.final_verify is not None:
        console.print("[bold yellow]⚠ The game still has issues on final verification:[/]")
        for check in outcome.final_verify.failures():
            console.print(f"  [red]assertion failed: {check}[/]")
        for line in outcome.final_verify.run.error_lines()[:8]:
            console.print(f"  [red]{line}[/]")
    else:
        console.print("[yellow]Could not run a final verification (is Godot installed?).[/]")

    console.print(f"\nProject: [bold]{outcome.project_dir}[/]")
    console.print(f"Open it in Godot: [dim]godot --editor --path {outcome.project_dir}[/]")
    console.print(
        'Next: [cyan]playsmith run[/], [cyan]playsmith edit "..."[/], '
        "or [cyan]playsmith export --target web[/]."
    )
    if not outcome.agent_result.done:
        console.print(f"[dim](agent stopped: {outcome.agent_result.reason})[/]")


@app.command()
def new(
    prompt: str = typer.Argument(..., help="What game to build, e.g. 'a 2D platformer...'."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Auto-approve all file writes."),
    config: str = typer.Option(None, "--config", "-c", help="Path to a config YAML."),
    max_iterations: int = typer.Option(24, "--max-iterations", help="Agent step cap."),
) -> None:
    """Turn a prompt into a real, runnable Godot 4 project (route -> generate -> verify)."""
    try:
        cfg = load_config(config)
    except ConfigError as exc:
        console.print(f"[bold red]Config error:[/] {exc}")
        raise typer.Exit(code=1) from exc

    try:
        outcome = new_game(
            prompt, config=cfg, auto_approve=yes, console=console, max_iterations=max_iterations
        )
    except EngineNotFoundError as exc:
        console.print(f"[bold red]Engine error:[/] {exc}")
        raise typer.Exit(code=1) from exc
    except LLMError as exc:
        console.print(f"[bold red]LLM error:[/] {exc}")
        console.print("[dim]Is your model running? Check `playsmith models`.[/]")
        raise typer.Exit(code=1) from exc

    _print_build_outcome(outcome)


@app.command()
def edit(
    change: str = typer.Argument(..., help='The change, e.g. "make the player jump higher".'),
    project: str = typer.Option(None, "--project", "-p", help="Project dir (default: latest)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Auto-approve all file writes."),
    config: str = typer.Option(None, "--config", "-c", help="Path to a config YAML."),
    max_iterations: int = typer.Option(24, "--max-iterations", help="Agent step cap."),
) -> None:
    """Iterate on an existing generated project in natural language (re-runs + re-verifies)."""
    try:
        cfg = load_config(config)
    except ConfigError as exc:
        console.print(f"[bold red]Config error:[/] {exc}")
        raise typer.Exit(code=1) from exc

    project_dir = _resolve_project(cfg, project)
    try:
        outcome = edit_game(
            change,
            config=cfg,
            project_dir=str(project_dir),
            auto_approve=yes,
            console=console,
            max_iterations=max_iterations,
        )
    except EngineNotFoundError as exc:
        console.print(f"[bold red]Engine error:[/] {exc}")
        raise typer.Exit(code=1) from exc
    except LLMError as exc:
        console.print(f"[bold red]LLM error:[/] {exc}")
        console.print("[dim]Is your model running? Check `playsmith models`.[/]")
        raise typer.Exit(code=1) from exc

    _print_build_outcome(outcome)


@app.command()
def run(
    project: str = typer.Option(None, "--project", "-p", help="Project dir (default: latest)."),
    config: str = typer.Option(None, "--config", "-c", help="Path to a config YAML."),
) -> None:
    """Run the most recent (or a given) generated project in a window so you can play it."""
    cfg = load_config(config)
    project_dir = _resolve_project(cfg, project)
    adapter = GodotAdapter(project_dir, binary=cfg.engine.godot.binary)
    console.print(f"Running [bold]{project_dir}[/] ...")
    try:
        result = adapter.run(headless=False, timeout_s=600)
    except (EngineError, EngineNotFoundError) as exc:
        console.print(f"[bold red]Engine error:[/] {exc}")
        raise typer.Exit(code=1) from exc
    if result.error_lines():
        console.print("[yellow]Engine reported errors:[/]")
        for line in result.error_lines()[:10]:
            console.print(f"  [red]{line}[/]")


_EXPORT_TARGETS = {
    "web": ExportTarget.WEB,
    "windows": ExportTarget.WINDOWS,
    "win": ExportTarget.WINDOWS,
    "mac": ExportTarget.MACOS,
    "macos": ExportTarget.MACOS,
    "linux": ExportTarget.LINUX,
}
_EXPORT_OUT_NAMES = {
    ExportTarget.WEB: "index.html",
    ExportTarget.WINDOWS: "game.exe",
    ExportTarget.MACOS: "game.zip",
    ExportTarget.LINUX: "game.x86_64",
}


@app.command()
def export(
    target: str = typer.Option("web", "--target", "-t", help="web | windows | mac | linux."),
    project: str = typer.Option(None, "--project", "-p", help="Project dir (default: latest)."),
    out: str = typer.Option(
        None, "--out", "-o", help="Output path (default: <project>/build/...)."
    ),
    config: str = typer.Option(None, "--config", "-c", help="Path to a config YAML."),
) -> None:
    """Headless export of the generated game (web HTML5 or a desktop build)."""
    cfg = load_config(config)
    key = target.lower()
    if key not in _EXPORT_TARGETS:
        console.print(
            f"[bold red]Unsupported target:[/] {target}. Try: {', '.join(sorted(_EXPORT_TARGETS))}."
        )
        console.print(
            "[dim](Android/iOS use `playsmith publish` — they need signing + store steps.)[/]"
        )
        raise typer.Exit(code=1)
    tgt = _EXPORT_TARGETS[key]
    project_dir = _resolve_project(cfg, project)
    out_path = Path(out).expanduser() if out else project_dir / "build" / _EXPORT_OUT_NAMES[tgt]
    adapter = GodotAdapter(project_dir, binary=cfg.engine.godot.binary)
    console.print(
        f"Exporting [bold]{project_dir}[/] ([cyan]{tgt.value}[/]) → [dim]{out_path}[/] ..."
    )
    try:
        result = adapter.export(tgt, str(out_path))
    except (EngineError, EngineNotFoundError) as exc:
        console.print(f"[bold red]Engine error:[/] {exc}")
        raise typer.Exit(code=1) from exc
    if out_path.exists() and result.returncode == 0:
        console.print(f"[bold green]✓ Exported[/] to {out_path}")
        if tgt is ExportTarget.WEB:
            console.print(f"Serve it: [dim]python -m http.server -d {out_path.parent}[/]")
        else:
            console.print(
                "[dim]Code-sign / notarize the build before distributing (see the store's docs).[/]"
            )
    else:
        console.print("[bold red]Export failed.[/] Logs:")
        console.print(result.logs or "(no output)")
        console.print(
            f"[dim]Tip: install Godot export templates for {tgt.value} "
            "(Editor → Manage Export Templates).[/]"
        )
        raise typer.Exit(code=1)


@app.command()
def publish(
    itch: str = typer.Option(None, "--itch", help="Publish to itch.io; target as user/game."),
    steam: str = typer.Option(None, "--steam", help="Publish to Steam; the app ID."),
    channel: str = typer.Option("web", "--channel", help="itch butler channel (default web)."),
    branch: str = typer.Option("beta", "--branch", help="Steam branch (default beta; never live)."),
    project: str = typer.Option(None, "--project", "-p", help="Project dir (default: latest)."),
    config: str = typer.Option(None, "--config", "-c", help="Path to a config YAML."),
) -> None:
    """Publish to itch.io (butler) or Steam (steamcmd), with compliance reminders."""
    cfg = load_config(config)
    if not itch and not steam:
        console.print(
            "Specify a target, e.g. `playsmith publish --itch you/game` or `--steam <appid>`."
        )
        raise typer.Exit(code=1)
    project_dir = _resolve_project(cfg, project)

    if steam:
        console.print(
            f"Publishing [bold]{project_dir.name}[/] → Steam app [cyan]{steam}[/] branch "
            f"[cyan]{branch}[/] (not live) ..."
        )
        try:
            publish_steam(
                project_dir,
                steam,
                branch=branch,
                steamcmd_path=cfg.publish.steamcmd_path,
                account=cfg.publish.steam_account,
                godot_binary=cfg.engine.godot.binary,
                console=console,
            )
        except (PublishError, EngineNotFoundError) as exc:
            console.print(f"[bold red]Publish failed:[/] {exc}")
            raise typer.Exit(code=1) from exc
        console.print(
            f"[bold green]Uploaded[/] to Steam app {steam} branch '{branch}'. "
            "Promote to the default branch manually in Steamworks when ready."
        )
        return

    console.print(f"Publishing [bold]{project_dir.name}[/] → itch.io [cyan]{itch}:{channel}[/] ...")
    try:
        publish_itch(
            project_dir,
            itch,
            channel=channel,
            butler_path=cfg.publish.butler_path,
            godot_binary=cfg.engine.godot.binary,
            console=console,
        )
    except (PublishError, EngineNotFoundError) as exc:
        console.print(f"[bold red]Publish failed:[/] {exc}")
        raise typer.Exit(code=1) from exc
    user, game = itch.split("/", 1)
    console.print(f"[bold green]Published[/] → https://{user}.itch.io/{game}")


unreal_app = typer.Typer(help="Unreal Engine track (EXPERIMENTAL; Godot is the default engine).")
app.add_typer(unreal_app, name="unreal")


@unreal_app.command("royalty")
def unreal_royalty(
    gross: float = typer.Argument(..., help="Lifetime gross revenue for the product (USD)."),
    egs: bool = typer.Option(False, "--egs", help="Launched via Epic Games Store (3.5% rate)."),
    egs_exempt: float = typer.Option(0.0, "--egs-exempt", help="Revenue earned on EGS (exempt)."),
) -> None:
    """Estimate Unreal EULA royalties (Godot has none, ever)."""
    est = royalty_estimate(gross, via_egs=egs, egs_exempt_revenue=egs_exempt)
    table = Table(title="Unreal royalty estimate", show_header=False)
    table.add_row("Gross revenue", f"${est['gross_revenue']:,.0f}")
    table.add_row("Royalty-free threshold", f"${est['threshold']:,.0f} per product")
    table.add_row("Rate", f"{est['rate'] * 100:.1f}%{' (EGS)' if est['via_egs'] else ''}")
    table.add_row("Royaltyable revenue", f"${est['royaltyable_revenue']:,.0f}")
    table.add_row("Estimated royalty owed", f"[bold]${est['royalty_owed']:,.2f}[/]")
    console.print(table)
    console.print("[dim]Godot charges no royalties, ever — this cost is Unreal-only.[/]")


@unreal_app.command("check")
def unreal_check(
    config: str = typer.Option(None, "--config", "-c", help="Path to a config YAML."),
) -> None:
    """Check the Unreal track: editor binary + Remote Control API availability."""
    load_config(config)
    adapter = UnrealAdapter("/tmp/_playsmith_unreal_check")
    try:
        ver = adapter.version()
        console.print(f"Found Unreal: [bold cyan]{ver}[/]")
    except (EngineNotFoundError, EngineError) as exc:
        console.print(f"[yellow]Unreal editor not available:[/] {exc}")
    rc = "[green]reachable[/]" if adapter.remote.available() else "[yellow]not reachable[/]"
    console.print(f"Remote Control API ({adapter.remote.host}): {rc}")
    console.print("[dim]The Unreal track is experimental; Godot is the default, tested engine.[/]")


def main() -> None:
    """Console-script entrypoint."""
    app()


if __name__ == "__main__":
    main()
