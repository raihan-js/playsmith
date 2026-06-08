"""Playsmith CLI entrypoint (Typer + Rich).

Commands are added incrementally as capabilities land (see BUILD_PLAN.md):
  version       — print version                                    [Step 1]
  config-check  — load and display the resolved configuration      [Step 1]
  models        — send a test message to the configured model      [Step 2]
  engine-check  — create + run a trivial Godot project headless    [Step 3]
  skills        — list installed game-generation skills            [Step 4]
  new           — prompt -> scaffold + generate + run-verify        [Step 6]
  run / export  — run or export the generated game                 [Step 7]
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from playsmith import __version__
from playsmith.config import Config, ConfigError, load_config
from playsmith.engines import EngineError, EngineNotFoundError, GodotAdapter, SceneSpec
from playsmith.engines.godot import templates as godot_templates
from playsmith.llm import LLMError, LLMGateway, Message

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
    table.add_row("llm.api_key", "<set>" if cfg.llm.api_key else "<empty>")
    table.add_row("engine.default", cfg.engine.default)
    table.add_row("engine.godot.binary", cfg.engine.godot.binary)
    table.add_row("assets.enabled", str(cfg.assets.enabled))
    console.print(table)


@app.command()
def models(
    config: str = typer.Option(None, "--config", "-c", help="Path to a config YAML."),
    prompt: str = typer.Option("Say hi in five words.", "--prompt", "-p", help="Message to send."),
) -> None:
    """Send a one-line message to the configured model to confirm it responds.

    This is the proof that the whole 'any local model' foundation works: with Ollama
    running, you should get a real reply from your local model.
    """
    try:
        cfg = load_config(config)
    except ConfigError as exc:
        console.print(f"[bold red]Config error:[/] {exc}")
        raise typer.Exit(code=1) from exc

    gateway = LLMGateway(cfg.llm)
    console.print(f"Asking [bold cyan]{cfg.llm.model}[/] at [dim]{cfg.llm.base_url}[/] ...")
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


def main() -> None:
    """Console-script entrypoint."""
    app()


if __name__ == "__main__":
    main()
