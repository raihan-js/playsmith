"""Playsmith CLI entrypoint (Typer + Rich).

Commands are added incrementally as capabilities land (see BUILD_PLAN.md):
  version       — print version                                    [Step 1]
  config-check  — load and display the resolved configuration      [Step 1]
  models        — send a test message to the configured model      [Step 2]
  engine-check  — create + run a trivial Godot project headless    [Step 3]
  skills        — list installed game-generation skills            [Step 4]
  new           — prompt -> scaffold + generate + run-verify        [Step 6]
  run           — run the latest generated project in a window      [Step 7]
  export        — headless HTML5 export of the generated game       [Step 7]
"""

from __future__ import annotations

import re
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from playsmith import __version__
from playsmith.assets import AssetError, ComfyUIClient
from playsmith.config import Config, ConfigError, load_config
from playsmith.engines import (
    EngineError,
    EngineNotFoundError,
    ExportTarget,
    GodotAdapter,
    SceneSpec,
)
from playsmith.engines.godot import templates as godot_templates
from playsmith.llm import LLMError, LLMGateway, Message
from playsmith.skills import SkillLoader
from playsmith.studio import latest_project, new_game

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
) -> None:
    """Show the configured providers/routes and round-trip a message to the default model.

    Proves the whole 'any model' foundation works: with Ollama running you get a real reply,
    and the table shows which provider each task type resolves to (router + cloud fallback).
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


@app.command()
def skills() -> None:
    """List the installed game-generation skills."""
    found = SkillLoader().discover()
    if not found:
        console.print("[yellow]No skills found under game-skills/.[/]")
        return
    table = Table(title="Installed skills", show_header=True, header_style="bold")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Description", style="white")
    for skill in found:
        desc = skill.description
        table.add_row(skill.name, desc if len(desc) <= 90 else desc[:87] + "...")
    console.print(table)


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
    kind: str = typer.Option("sprite", "--kind", "-k", help="sprite|portrait|background|tileset."),
    project: str = typer.Option(None, "--project", "-p", help="Project dir (default: latest)."),
    out: str = typer.Option(
        None, "--out", "-o", help="Output path (default <project>/assets/...)."
    ),
    config: str = typer.Option(None, "--config", "-c", help="Path to a config YAML."),
) -> None:
    """Generate a 2D asset via ComfyUI into a project (graceful if ComfyUI isn't running)."""
    cfg = load_config(config)
    client = ComfyUIClient(cfg.assets.comfyui_url, model=cfg.assets.model)
    if not client.available():
        console.print(
            f"[yellow]ComfyUI not reachable at {cfg.assets.comfyui_url}.[/] "
            "Games still ship with placeholders."
        )
        console.print("[dim]Start ComfyUI and set assets.comfyui_url to generate real sprites.[/]")
        raise typer.Exit(code=1)
    project_dir = _resolve_project(cfg, project)
    safe = re.sub(r"[^a-z0-9]+", "_", prompt.lower()).strip("_")[:40] or "asset"
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
        "Next: [cyan]playsmith run[/] to play it, [cyan]playsmith export --target web[/]."
    )
    if not outcome.agent_result.done:
        console.print(f"[dim](agent stopped: {outcome.agent_result.reason})[/]")


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


@app.command()
def export(
    target: str = typer.Option("web", "--target", "-t", help="Export target (web)."),
    project: str = typer.Option(None, "--project", "-p", help="Project dir (default: latest)."),
    out: str = typer.Option(
        None, "--out", "-o", help="Output path (default: <project>/build/...)."
    ),
    config: str = typer.Option(None, "--config", "-c", help="Path to a config YAML."),
) -> None:
    """Headless export of the generated game (Web/HTML5 at MVP)."""
    cfg = load_config(config)
    if target.lower() != "web":
        console.print(f"[bold red]Unsupported target:[/] {target}. Only 'web' is supported at MVP.")
        raise typer.Exit(code=1)
    project_dir = _resolve_project(cfg, project)
    out_path = Path(out).expanduser() if out else project_dir / "build" / "index.html"
    adapter = GodotAdapter(project_dir, binary=cfg.engine.godot.binary)
    console.print(f"Exporting [bold]{project_dir}[/] → [dim]{out_path}[/] ...")
    try:
        result = adapter.export(ExportTarget.WEB, str(out_path))
    except (EngineError, EngineNotFoundError) as exc:
        console.print(f"[bold red]Engine error:[/] {exc}")
        raise typer.Exit(code=1) from exc
    if out_path.exists() and result.returncode == 0:
        console.print(f"[bold green]✓ Exported[/] to {out_path}")
        console.print(f"Serve it: [dim]python -m http.server -d {out_path.parent}[/]")
    else:
        console.print("[bold red]Export failed.[/] Logs:")
        console.print(result.logs or "(no output)")
        console.print(
            "[dim]Tip: install Godot export templates "
            "(Editor → Manage Export Templates) for HTML5.[/]"
        )
        raise typer.Exit(code=1)


def main() -> None:
    """Console-script entrypoint."""
    app()


if __name__ == "__main__":
    main()
