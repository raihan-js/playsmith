"""Playsmith CLI entrypoint (Typer + Rich).

Command surface:
  version       — print version
  config-check  — show the resolved configuration (providers, routes, fallback)
  models        — route table + round-trip the default model (--eval for reliability)
  skills        — list / search / install / remove game-generation skills (marketplace)
  unreal        — the Unreal Engine track: new (build + verify), check, royalty calculator
"""

from __future__ import annotations

import re
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from playsmith import __version__
from playsmith.config import Config, ConfigError, load_config
from playsmith.engines import EngineError, EngineNotFoundError
from playsmith.engines.unreal import UnrealAdapter, level_director, royalty_estimate
from playsmith.llm import LLMError, LLMGateway, Message
from playsmith.llm.eval import evaluate_targets
from playsmith.skills import SkillLoader, SkillRegistry, SkillRegistryError

app = typer.Typer(
    name="playsmith",
    help="Turn a plain prompt into a real, editable, shippable Unreal Engine game — locally.",
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
    table.add_row("engine.unreal.editor_cmd", cfg.engine.unreal.editor_cmd)
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


unreal_app = typer.Typer(help="The Unreal Engine track: build + verify, check, royalty calculator.")
app.add_typer(unreal_app, name="unreal")


@unreal_app.command("royalty")
def unreal_royalty(
    gross: float = typer.Argument(..., help="Lifetime gross revenue for the product (USD)."),
    egs: bool = typer.Option(False, "--egs", help="Launched via Epic Games Store (3.5% rate)."),
    egs_exempt: float = typer.Option(0.0, "--egs-exempt", help="Revenue earned on EGS (exempt)."),
) -> None:
    """Estimate Unreal EULA royalties (5% above $1M lifetime gross per product; 3.5% via EGS)."""
    est = royalty_estimate(gross, via_egs=egs, egs_exempt_revenue=egs_exempt)
    table = Table(title="Unreal royalty estimate", show_header=False)
    table.add_row("Gross revenue", f"${est['gross_revenue']:,.0f}")
    table.add_row("Royalty-free threshold", f"${est['threshold']:,.0f} per product")
    table.add_row("Rate", f"{est['rate'] * 100:.1f}%{' (EGS)' if est['via_egs'] else ''}")
    table.add_row("Royaltyable revenue", f"${est['royaltyable_revenue']:,.0f}")
    table.add_row("Estimated royalty owed", f"[bold]${est['royalty_owed']:,.2f}[/]")
    console.print(table)


@unreal_app.command("check")
def unreal_check(
    config: str = typer.Option(None, "--config", "-c", help="Path to a config YAML."),
) -> None:
    """Check the Unreal track: editor binary + Remote Control API availability."""
    cfg = load_config(config)
    adapter = UnrealAdapter("/tmp/_playsmith_unreal_check", editor_cmd=cfg.engine.unreal.editor_cmd)
    try:
        ver = adapter.version()
        console.print(f"Found Unreal: [bold cyan]{ver}[/]")
    except (EngineNotFoundError, EngineError) as exc:
        console.print(f"[yellow]Unreal editor not available:[/] {exc}")
    rc = "[green]reachable[/]" if adapter.remote.available() else "[yellow]not reachable[/]"
    console.print(f"Remote Control API ({adapter.remote.host}): {rc}")


@unreal_app.command("new")
def unreal_new(
    name: str = typer.Argument(..., help="A name for the game/project."),
    config: str = typer.Option(None, "--config", "-c", help="Path to a config YAML."),
) -> None:
    """Scaffold + verify a real, playable Unreal 5.x project (floor + PlayerStart + pawn).

    Drives your local UnrealEditor-Cmd headless via the UE Python API, builds a deterministic
    playable level, and verifies it in-engine (the assertion-based reality loop, CLAUDE.md §4).
    Set engine.unreal.editor_cmd in your config to your UnrealEditor-Cmd path.
    """
    cfg = load_config(config)
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "unreal-game"
    project_dir = cfg.workspace_dir.expanduser() / slug
    adapter = UnrealAdapter(project_dir, editor_cmd=cfg.engine.unreal.editor_cmd)
    console.print(f"Creating Unreal project at [dim]{project_dir}[/] ...")
    adapter.create_project(name)

    # Theme the level from the prompt (best-effort; falls back to a safe default level).
    spec = None
    try:
        gateway = LLMGateway.from_config(cfg, console=console)
        console.print("Designing the level from your prompt ...")
        spec = level_director.plan_level(name, gateway)
        console.print(
            f"  theme: [cyan]{spec.get('theme', '')}[/] · "
            f"{len(spec.get('obstacles', []))} obstacles"
        )
    except (LLMError, OSError):
        console.print("[dim]LLM unavailable — building a default level.[/]")

    console.print("Scaffolding a lit, playable level (UE headless — first build is slow) ...")
    try:
        adapter.scaffold(spec)
        console.print("Verifying the level in-engine ...")
        result = adapter.verify(
            checks=[
                "level_loads",
                "player_start_exists",
                "floor_exists",
                "player_exists",
                "goal_exists",
            ]
        )
    except EngineNotFoundError as exc:
        console.print(f"[bold red]{exc}[/]")
        console.print(
            "[dim]Set engine.unreal.editor_cmd to your full UnrealEditor-Cmd path in the config.[/]"
        )
        raise typer.Exit(code=1) from exc
    table = Table(title="Unreal verify", show_header=False)
    for key, value in result.assertions.items():
        table.add_row(key, "[green]PASS[/]" if value else "[red]FAIL[/]")
    console.print(table)
    if result.ok:
        uproj = next(project_dir.glob("*.uproject"), None)
        console.print(f"[bold green]✓ Real, verified Unreal project[/] at [dim]{project_dir}[/]")
        console.print(f"[dim]Open it in the editor: UnrealEditor {uproj}[/]")
    else:
        console.print("[yellow]Some checks failed — see the table above.[/]")
        raise typer.Exit(code=1)


def main() -> None:
    """Console-script entrypoint."""
    app()


if __name__ == "__main__":
    main()
