"""Studio — the orchestrator that turns a prompt into a real, runnable game.

This is where the pillars meet (docs/ARCHITECTURE.md "Data flow"):

    prompt -> skills.route -> agent.run(goal=skill.body, tools=[fs, engine])
              loop: write code -> engine.run() -> read logs -> fix
           -> final reality check -> report where the project is

Keep this layer thin: it wires modules together and owns no engine/model specifics.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

from playsmith.agent import AgentLoop, AgentResult, AutoApprover, InteractiveApprover, ToolContext
from playsmith.agent.approval import Approver
from playsmith.agent.tools import scan_assets
from playsmith.assets import get_asset_generator, get_mesh_generator
from playsmith.config import Config, load_config
from playsmith.engines import EngineError, GodotAdapter
from playsmith.engines.base import EngineAdapter, RunResult, VerifyResult
from playsmith.llm import LLMGateway
from playsmith.skills import Skill, SkillLoader, SkillRouter

_ENGINE_CHECK_DIR = "_playsmith_engine_check"
# Per-project metadata (which skill made it, its assertions) — lets `edit` verify correctly.
# Godot ignores dot-directories, so this never interferes with the game project.
_MANIFEST_PATH = ".playsmith/manifest.json"


def write_manifest(
    project_dir: Path, *, skill: str | None, prompt: str, assertions: list[str]
) -> None:
    path = Path(project_dir) / _MANIFEST_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"skill": skill, "prompt": prompt, "assertions": assertions}, indent=2)
    )


def read_manifest(project_dir: Path) -> dict | None:
    path = Path(project_dir) / _MANIFEST_PATH
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


@dataclass
class BuildOutcome:
    """The result of a `playsmith new` build."""

    project_dir: Path
    skill_name: str | None
    agent_result: AgentResult
    final_verify: VerifyResult | None

    @property
    def runs_clean(self) -> bool:
        return self.final_verify is not None and self.final_verify.ok

    @property
    def final_run(self) -> RunResult | None:
        return self.final_verify.run if self.final_verify else None


def _emit(on_event: Callable[[dict], None] | None, payload: dict) -> None:
    if on_event is not None:
        try:
            on_event(payload)
        except Exception:  # noqa: BLE001 - a broken sink must never break a build
            pass


def slugify(text: str, *, fallback: str = "game") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    slug = "-".join(slug.split("-")[:6])  # keep it short
    return slug[:48] or fallback


def _title(text: str) -> str:
    words = re.sub(r"[^A-Za-z0-9 ]+", " ", text).split()
    return " ".join(words[:6]).title() or "Playsmith Game"


def build_goal(
    prompt: str, skill: Skill | None, project_dir: Path, scaffolded: list[str] | None = None
) -> str:
    """Assemble the goal handed to the agent: scaffolding note + skill body + the ask."""
    scaffolded = scaffolded or []
    if scaffolded:
        opening = (
            f"Personalize the game in the Godot 4 project at: {project_dir}\n"
            "A COMPLETE, ALREADY-PLAYABLE game exists here (main scene res://Main.tscn with a "
            "player, floor, platforms, coins, spikes, a goal, and a score HUD); it RUNS and PASSES "
            "verification. Your ONLY job is to personalize it with SMALL, SAFE edits.\n"
            "STRICT RULES:\n"
            "- Do NOT create new .tscn files by hand, and do NOT rewrite these files: "
            + ", ".join(scaffolded)
            + ".\n- Make small edits with apply_patch only: tweak colors/positions/counts, or add "
            "a coin/platform by copying an existing node block in Main.tscn.\n"
            "- To add BEHAVIOR, edit the GDScript (scripts/game.gd, scripts/player.gd), never the "
            "scene text.\n"
            "- GRAPHICS: a themed background is already generated and applied for you. You MAY "
            "generate a player sprite with generate_asset(kind=sprite) and save it to "
            "res://assets/player.png — it is auto-applied at runtime, so do NOT edit scene files "
            "for art. Verify after any change.\n"
            "- After EVERY change call run_engine + verify_game. If a change makes verification "
            "FAIL, UNDO it immediately and try something smaller.\n"
            "- If you can't improve it safely, just call task_complete — the base game is good."
        )
    else:
        opening = (
            f"Build a game in the Godot 4 project at: {project_dir}\n"
            "project.godot exists; main scene is res://Main.tscn. Create that Main.tscn plus the "
            "scenes/scripts the game needs, then run_engine + verify_game and fix until it passes."
        )
    parts = [opening, "", f"USER REQUEST:\n{prompt}"]
    if skill is not None:
        parts.append(f"\nFOLLOW THIS SKILL — {skill.name}:\n{skill.body()}")
        if "scripts/player.gd" not in scaffolded:
            try:
                template = skill.read_script("player.gd")
                parts.append(
                    "\nMOVEMENT TEMPLATE — write this as scripts/player.gd (tune the constants):\n"
                    "```gdscript\n" + template + "\n```"
                )
            except Exception:  # noqa: BLE001 - template is a nicety, not required
                pass
    imported = scan_assets(project_dir)
    if imported:
        parts.append(
            "\nIMPORTED ART — use these textures/sounds instead of placeholders:\n"
            + "\n".join(imported)
        )
    if skill is not None and skill.assertions:
        parts.append(
            "\nThese assertions must PASS (call verify_game): "
            + ", ".join(skill.assertions)
            + ". If any fails, fix it and verify again."
        )
    parts.append(
        "\nOnce verify_game reports every assertion PASS, call task_complete with a short summary."
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
    on_event: Callable[[dict], None] | None = None,
) -> BuildOutcome:
    """Route, scaffold, run the agent, then do a final authoritative reality check."""
    cfg = config or load_config()
    console = console or Console()
    gateway = gateway or LLMGateway.from_config(cfg, console=console)
    router = router or SkillRouter(SkillLoader(), gateway)

    skill = router.route(prompt)
    if verbose:
        console.print(f"Skill: [bold cyan]{skill.name if skill else '(none — generic build)'}[/]")
    _emit(
        on_event, {"type": "phase", "text": f"Routed to skill: {skill.name if skill else 'none'}"}
    )
    if skill is not None and not skill.trusted:
        console.print(
            f"[yellow]⚠ '{skill.name}' is a community skill from {skill.source}. Its instructions "
            "drive the agent and its scripts will be written into your game — review the diffs.[/]"
        )

    name = project_name or slugify(prompt)
    project_dir = cfg.workspace_dir.expanduser() / name
    if adapter is None:
        adapter = GodotAdapter(project_dir, binary=cfg.engine.godot.binary)
    adapter.create_project(_title(prompt), main_scene="res://Main.tscn")
    # Deterministic scaffolding: write the skill's bundled scripts + starter scenes verbatim so the
    # base game already RUNS. The agent then embellishes instead of hand-writing brittle .tscn —
    # the single biggest reliability lever (WHY.md "lean on deterministic scaffolding").
    scaffolded: list[str] = []
    scaffold_contents: dict[str, str] = {}  # kept so we can restore the base if the agent breaks it
    if skill is not None:
        for script_name in skill.scripts():
            content = skill.read_script(script_name)
            adapter.write_script(f"scripts/{script_name}", content)
            scaffolded.append(f"scripts/{script_name}")
            scaffold_contents[f"scripts/{script_name}"] = content
        for rel, path in skill.starter_files().items():
            content = path.read_text()
            adapter.write_script(rel, content)
            scaffolded.append(rel)
            scaffold_contents[rel] = content
    if verbose:
        console.print(f"Project: [dim]{adapter.project_dir}[/]")
        if scaffolded:
            console.print(f"Scaffolded a working base: [dim]{', '.join(scaffolded)}[/]")
    if scaffolded:
        _emit(
            on_event,
            {"type": "phase", "text": f"Scaffolded a working base ({len(scaffolded)} files)"},
        )

    # Reliable graphics: generate a themed background + import it. game.gd applies it at runtime
    # from res://assets/background.png, so every game looks real — no brittle scene edits.
    asset_gen = get_asset_generator(cfg)
    if asset_gen is not None and scaffolded:
        try:
            if asset_gen.available():
                asset_gen.image(
                    prompt, "background", str(adapter.project_dir / "assets" / "background.png")
                )
                adapter.import_assets()
                if verbose:
                    console.print("Generated a themed background.")
                _emit(on_event, {"type": "phase", "text": "Generated a themed background"})
        except Exception:  # noqa: BLE001 - art is optional; never block a build
            pass

    if approver is None:
        approver = AutoApprover() if auto_approve else InteractiveApprover(console)
    ctx = ToolContext(
        adapter=adapter,
        approver=approver,
        asset_generator=asset_gen,
        mesh_generator=get_mesh_generator(cfg),
    )
    loop = AgentLoop(
        gateway,
        ctx,
        max_iterations=max_iterations,
        console=console,
        verbose=verbose,
        on_event=on_event,
    )
    agent_result = loop.run(build_goal(prompt, skill, adapter.project_dir, scaffolded))

    # Record what made this project so `playsmith edit` can verify it correctly later.
    try:
        write_manifest(
            adapter.project_dir,
            skill=skill.name if skill else None,
            prompt=prompt,
            assertions=skill.assertions if skill else [],
        )
    except OSError:
        pass

    # Final authoritative verification (assertion-based), independent of the agent's claim.
    checks = skill.assertions if (skill and skill.assertions) else None
    final_verify: VerifyResult | None = None
    try:
        final_verify = adapter.verify(checks=checks)
    except EngineError as exc:
        if verbose:
            console.print(f"[yellow]Final verification could not run:[/] {exc}")

    # Safety net: if the agent broke the playable base, restore the scaffolded files so a working
    # game still ships (the agent's additions are reverted, but the base is a complete game).
    if final_verify is not None and not final_verify.ok and scaffold_contents:
        for rel, content in scaffold_contents.items():
            adapter.write_script(rel, content)
        try:
            restored = adapter.verify(checks=checks)
        except EngineError:
            restored = None
        if restored is not None and restored.ok:
            final_verify = restored
            if verbose:
                console.print(
                    "[yellow]Agent changes failed verification — restored the working base game.[/]"
                )
            _emit(
                on_event,
                {"type": "phase", "text": "Agent changes failed — restored the working base game."},
            )

    outcome = BuildOutcome(
        project_dir=Path(adapter.project_dir),
        skill_name=skill.name if skill else None,
        agent_result=agent_result,
        final_verify=final_verify,
    )
    _emit(on_event, _outcome_event(outcome))
    return outcome


def _outcome_event(outcome: BuildOutcome) -> dict:
    return {
        "type": "done",
        "done": outcome.agent_result.done,
        "runs_clean": outcome.runs_clean,
        "project": outcome.project_dir.name,
        "project_path": str(outcome.project_dir),
        "skill": outcome.skill_name,
        "assertions": dict(outcome.final_verify.assertions) if outcome.final_verify else {},
        "summary": outcome.agent_result.summary,
        "reason": outcome.agent_result.reason,
    }


def build_edit_goal(change: str, project_dir: Path, assertions: list[str] | None) -> str:
    """The goal for iterating on an existing project in natural language."""
    parts = [
        f"Here is an EXISTING Godot 4 project at: {project_dir}",
        "First use list_dir and read_file to understand its scenes and scripts. Then make this "
        "change with apply_patch/write_file:",
        f"\nCHANGE REQUESTED:\n{change}",
        "\nAfter editing, call run_engine and verify_game, and fix until it runs with no errors.",
    ]
    imported = scan_assets(project_dir)
    if imported:
        parts.append(
            "\nIMPORTED ART available — prefer these over placeholders:\n" + "\n".join(imported)
        )
    if assertions:
        parts.append("\nKeep these assertions PASSING: " + ", ".join(assertions))
    parts.append(
        "\nWhen verify_game passes, call task_complete with a short summary of what changed."
    )
    return "\n".join(parts)


def edit_game(
    change: str,
    *,
    config: Config | None = None,
    gateway: LLMGateway | None = None,
    adapter: EngineAdapter | None = None,
    project_dir: str | Path | None = None,
    approver: Approver | None = None,
    auto_approve: bool = False,
    console: Console | None = None,
    max_iterations: int = 24,
    verbose: bool = True,
    on_event: Callable[[dict], None] | None = None,
) -> BuildOutcome:
    """Apply a natural-language change to an existing project, then verify it still works."""
    cfg = config or load_config()
    console = console or Console()
    gateway = gateway or LLMGateway.from_config(cfg, console=console)

    if adapter is None:
        target = (
            Path(project_dir).expanduser()
            if project_dir is not None
            else latest_project(cfg.workspace_dir)
        )
        if target is None:
            raise EngineError(
                'No project to edit. Run `playsmith new "..."` first, or pass --project.'
            )
        adapter = GodotAdapter(target, binary=cfg.engine.godot.binary)

    manifest = read_manifest(adapter.project_dir) or {}
    checks = manifest.get("assertions") or None
    skill_name = manifest.get("skill")
    if verbose:
        console.print(f"Editing: [dim]{adapter.project_dir}[/]")

    if approver is None:
        approver = AutoApprover() if auto_approve else InteractiveApprover(console)
    ctx = ToolContext(
        adapter=adapter,
        approver=approver,
        asset_generator=get_asset_generator(cfg),
        mesh_generator=get_mesh_generator(cfg),
    )
    loop = AgentLoop(
        gateway,
        ctx,
        max_iterations=max_iterations,
        console=console,
        verbose=verbose,
        on_event=on_event,
    )
    agent_result = loop.run(build_edit_goal(change, adapter.project_dir, checks))

    final_verify: VerifyResult | None = None
    try:
        final_verify = adapter.verify(checks=checks)
    except EngineError as exc:
        if verbose:
            console.print(f"[yellow]Final verification could not run:[/] {exc}")

    outcome = BuildOutcome(
        project_dir=Path(adapter.project_dir),
        skill_name=skill_name,
        agent_result=agent_result,
        final_verify=final_verify,
    )
    _emit(on_event, _outcome_event(outcome))
    return outcome


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
