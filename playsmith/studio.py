"""Studio — the orchestrator that turns a prompt into a real, runnable game.

This is where the pillars meet (docs/ARCHITECTURE.md "Data flow"):

    prompt -> skills.route -> agent.run(goal=skill.body, tools=[fs, engine])
              loop: write code -> engine.run() -> read logs -> fix
           -> final reality check -> report where the project is

Keep this layer thin: it wires modules together and owns no engine/model specifics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

from playsmith.agent import AgentLoop, AgentResult, AutoApprover, InteractiveApprover, ToolContext
from playsmith.agent.approval import Approver
from playsmith.config import Config, load_config
from playsmith.engines import EngineError, GodotAdapter
from playsmith.engines.base import EngineAdapter, RunResult
from playsmith.llm import LLMGateway
from playsmith.skills import Skill, SkillLoader, SkillRouter

_ENGINE_CHECK_DIR = "_playsmith_engine_check"


@dataclass
class BuildOutcome:
    """The result of a `playsmith new` build."""

    project_dir: Path
    skill_name: str | None
    agent_result: AgentResult
    final_run: RunResult | None

    @property
    def runs_clean(self) -> bool:
        return self.final_run is not None and self.final_run.ok


def slugify(text: str, *, fallback: str = "game") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    slug = "-".join(slug.split("-")[:6])  # keep it short
    return slug[:48] or fallback


def _title(text: str) -> str:
    words = re.sub(r"[^A-Za-z0-9 ]+", " ", text).split()
    return " ".join(words[:6]).title() or "Playsmith Game"


def build_goal(prompt: str, skill: Skill | None, project_dir: Path) -> str:
    """Assemble the goal handed to the agent: skill body + movement template + the ask."""
    parts = [
        f"Build a game in the Godot 4 project at: {project_dir}",
        "project.godot already exists and its main scene is res://Main.tscn. "
        "Create that Main.tscn plus the scenes/scripts the game needs, then RUN it and fix "
        "until it works with no errors.",
        "",
        f"USER REQUEST:\n{prompt}",
    ]
    if skill is not None:
        parts.append(f"\nFOLLOW THIS SKILL — {skill.name}:\n{skill.body()}")
        try:
            template = skill.read_script("player.gd")
            parts.append(
                "\nMOVEMENT TEMPLATE — write this as scripts/player.gd (tune the constants):\n"
                "```gdscript\n" + template + "\n```"
            )
        except Exception:  # noqa: BLE001 - template is a nicety, not required
            pass
    parts.append(
        "\nWhen the game runs cleanly and the player can stand on ground and jump, "
        "call task_complete with a one-line summary."
    )
    return "\n".join(parts)


def new_game(
    prompt: str,
    *,
    config: Config | None = None,
    gateway: LLMGateway | None = None,
    adapter: EngineAdapter | None = None,
    router: SkillRouter | None = None,
    approver: Approver | None = None,
    auto_approve: bool = False,
    console: Console | None = None,
    max_iterations: int = 24,
    project_name: str | None = None,
    verbose: bool = True,
) -> BuildOutcome:
    """Route, scaffold, run the agent, then do a final authoritative reality check."""
    cfg = config or load_config()
    console = console or Console()
    gateway = gateway or LLMGateway(cfg.llm)
    router = router or SkillRouter(SkillLoader(), gateway)

    skill = router.route(prompt)
    if verbose:
        console.print(f"Skill: [bold cyan]{skill.name if skill else '(none — generic build)'}[/]")

    name = project_name or slugify(prompt)
    project_dir = cfg.workspace_dir.expanduser() / name
    if adapter is None:
        adapter = GodotAdapter(project_dir, binary=cfg.engine.godot.binary)
    # Deterministic scaffold: the engine config (not game code) is created for the agent.
    adapter.create_project(_title(prompt), main_scene="res://Main.tscn")
    if verbose:
        console.print(f"Project: [dim]{adapter.project_dir}[/]")

    if approver is None:
        approver = AutoApprover() if auto_approve else InteractiveApprover(console)
    ctx = ToolContext(adapter=adapter, approver=approver)
    loop = AgentLoop(gateway, ctx, max_iterations=max_iterations, console=console, verbose=verbose)
    agent_result = loop.run(build_goal(prompt, skill, adapter.project_dir))

    # Final authoritative verification, independent of whatever the agent claimed.
    final_run: RunResult | None = None
    try:
        final_run = adapter.run(headless=True, timeout_s=30)
    except EngineError as exc:
        if verbose:
            console.print(f"[yellow]Final verification could not run:[/] {exc}")

    return BuildOutcome(
        project_dir=Path(adapter.project_dir),
        skill_name=skill.name if skill else None,
        agent_result=agent_result,
        final_run=final_run,
    )


def latest_project(workspace_dir: Path) -> Path | None:
    """The most recently modified generated project (ignoring the engine-check scratch dir)."""
    workspace = workspace_dir.expanduser()
    if not workspace.is_dir():
        return None
    candidates = [
        p
        for p in workspace.iterdir()
        if p.is_dir() and p.name != _ENGINE_CHECK_DIR and (p / "project.godot").exists()
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)
