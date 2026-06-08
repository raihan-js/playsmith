"""Agent tools — the actions the model may take, all confined to the game workspace.

Filesystem tools (read/write/list/patch) are scoped to the engine's ``project_dir``;
engine actions (run/screenshot) go through the :class:`EngineAdapter` (CLAUDE.md §6).
Each handler returns a short string that is fed back to the model as the tool result, so
the model can observe and self-correct — the reality loop (CLAUDE.md §4).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from playsmith.agent.approval import Approver, make_diff
from playsmith.assets.base import AssetError, AssetGenerator
from playsmith.engines.base import EngineAdapter, EngineError, RunResult, VerifyResult
from playsmith.llm import Tool, ToolCall

_MAX_RESULT_CHARS = 4000


class ToolError(Exception):
    """A recoverable tool failure; its message is returned to the model."""


def _truncate(text: str, limit: int = _MAX_RESULT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return "...[truncated]...\n" + text[-limit:]


@dataclass
class ToolContext:
    """Shared state the tools read and mutate during one agent run."""

    adapter: EngineAdapter
    approver: Approver
    asset_generator: AssetGenerator | None = None
    last_run: RunResult | None = None
    last_verify: VerifyResult | None = None
    last_screenshot: Path | None = None
    files_written: list[str] = field(default_factory=list)

    @property
    def workspace(self) -> Path:
        return self.adapter.project_dir

    def resolve(self, rel_path: str) -> Path:
        """Resolve a project-relative path, refusing escapes outside the workspace."""
        rel = rel_path.replace("res://", "").lstrip("/")
        target = (self.workspace / rel).resolve()
        if target != self.workspace and self.workspace not in target.parents:
            raise ToolError(f"Path '{rel_path}' is outside the project workspace.")
        return target


# -- individual tool handlers ----------------------------------------------------
def _read_file(args: dict, ctx: ToolContext) -> str:
    path = ctx.resolve(args["path"])
    if not path.exists():
        return f"File not found: {args['path']}"
    return _truncate(path.read_text())


def _list_dir(args: dict, ctx: ToolContext) -> str:
    path = ctx.resolve(args.get("path", "."))
    if not path.exists():
        return f"Directory not found: {args.get('path', '.')}"
    entries = []
    for p in sorted(path.iterdir()):
        entries.append(f"{p.name}/" if p.is_dir() else p.name)
    return "\n".join(entries) if entries else "(empty)"


def _write_file(args: dict, ctx: ToolContext) -> str:
    rel = args["path"]
    content = args["content"]
    path = ctx.resolve(rel)
    old = path.read_text() if path.exists() else ""
    if old == content:
        return f"No change: {rel} already has that content."
    if not ctx.approver.approve(rel, make_diff(rel, old, content)):
        return f"User rejected the change to {rel}. Do not retry it; consider an alternative."
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    ctx.files_written.append(rel)
    return f"Wrote {len(content)} bytes to {rel}."


def _apply_patch(args: dict, ctx: ToolContext) -> str:
    """Targeted edit: replace an exact substring. More reliable than unified diffs for LLMs."""
    rel = args["path"]
    find = args["find"]
    replace = args["replace"]
    path = ctx.resolve(rel)
    if not path.exists():
        return f"File not found: {rel}. Use write_file to create it."
    old = path.read_text()
    count = old.count(find)
    if count == 0:
        return f"The 'find' text was not present in {rel}. Re-read the file and try again."
    if count > 1:
        return f"The 'find' text appears {count} times in {rel}; make it unique."
    new = old.replace(find, replace, 1)
    if not ctx.approver.approve(rel, make_diff(rel, old, new)):
        return f"User rejected the edit to {rel}."
    path.write_text(new)
    ctx.files_written.append(rel)
    return f"Patched {rel}."


def _run_engine(args: dict, ctx: ToolContext) -> str:
    headless = bool(args.get("headless", True))
    scene = args.get("scene")
    try:
        result = ctx.adapter.run(headless=headless, scene=scene, timeout_s=30)
    except EngineError as exc:
        return f"Engine could not run: {exc}"
    ctx.last_run = result
    status = "OK" if result.ok else "PROBLEM"
    errors = result.error_lines()
    parts = [
        f"Run finished: {status} (exit={result.returncode}, timed_out={result.timed_out}).",
    ]
    if errors:
        parts.append("Errors detected:\n" + "\n".join(errors[:20]))
    parts.append("Logs:\n" + _truncate(result.logs or "(no output)", 2500))
    return "\n".join(parts)


def _screenshot(args: dict, ctx: ToolContext) -> str:
    out = ctx.workspace / "_playsmith_shot.png"
    try:
        result = ctx.adapter.screenshot(str(out), scene=args.get("scene"))
    except EngineError as exc:
        return f"Could not screenshot: {exc}"
    ctx.last_screenshot = out
    note = "" if result.ok else f" (engine reported: {'; '.join(result.error_lines()[:3])})"
    return f"Saved screenshot to {out}.{note}"


def _read_logs(args: dict, ctx: ToolContext) -> str:
    if ctx.last_run is None:
        return "No run yet. Call run_engine first."
    return _truncate(ctx.last_run.logs or "(no output)", 3000)


def _verify_game(args: dict, ctx: ToolContext) -> str:
    checks = args.get("checks") or None
    if isinstance(checks, str):
        checks = [c.strip() for c in checks.split(",") if c.strip()]
    try:
        result = ctx.adapter.verify(checks=checks, scene=args.get("scene"))
    except EngineError as exc:
        return f"Could not verify: {exc}"
    ctx.last_verify = result
    lines = [f"  {key}: {'PASS' if ok else 'FAIL'}" for key, ok in result.assertions.items()]
    if result.ok:
        header = "All gameplay assertions PASSED — the game actually works."
    elif result.assertions:
        header = (
            "FAILED: " + ", ".join(result.failures()) + ". Fix these and call verify_game again."
        )
    else:
        header = "No assertions were evaluated (is there a player/main scene yet?)."
    return header + ("\n" + "\n".join(lines) if lines else "")


_ASSET_EXTS = frozenset(
    {".png", ".jpg", ".jpeg", ".webp", ".svg", ".bmp", ".tga", ".ogg", ".wav", ".mp3"}
)


def scan_assets(root: Path) -> list[str]:
    """List image/audio asset files in a project as ``res://`` paths (skips our harnesses)."""
    out: list[str] = []
    for path in sorted(root.rglob("*")):
        if (
            path.is_file()
            and path.suffix.lower() in _ASSET_EXTS
            and not path.name.startswith("_playsmith")
        ):
            out.append("res://" + path.relative_to(root).as_posix())
    return out


def _list_assets(args: dict, ctx: ToolContext) -> str:
    found = scan_assets(ctx.workspace)
    if not found:
        return (
            "No imported art found. Use colored placeholders (ColorRect / a Sprite2D with a "
            "PlaceholderTexture2D). The user can add real art with `playsmith assets import`."
        )
    return "Imported art available — reference these instead of placeholders:\n" + "\n".join(found)


_PLACEHOLDER_MSG = (
    "Asset generation is unavailable. Use a colored placeholder (a Sprite2D with a "
    "PlaceholderTexture2D, or a ColorRect). A runnable game with placeholders beats a "
    "pretty one that doesn't run."
)


def _generate_asset(args: dict, ctx: ToolContext) -> str:
    gen = ctx.asset_generator
    prompt = (args.get("prompt") or "").strip()
    kind = args.get("kind") or "sprite"
    if not prompt:
        return "Provide a 'prompt' describing the art to generate."
    if gen is None or not gen.available():
        return _PLACEHOLDER_MSG
    safe = re.sub(r"[^a-z0-9]+", "_", prompt.lower()).strip("_")[:40] or "asset"
    dest = ctx.workspace / "assets" / f"{safe}.png"
    try:
        gen.image(prompt, kind, str(dest))
    except (AssetError, NotImplementedError, OSError) as exc:
        return f"Asset generation failed ({exc}). Use a placeholder instead."
    rel = dest.relative_to(ctx.workspace).as_posix()
    return f"Generated res://{rel}. Use it as the texture of a Sprite2D."


@dataclass
class _ToolDef:
    tool: Tool
    handler: Callable[[dict, ToolContext], str]
    sentinel: bool = False  # task_complete uses this to end the loop


def _obj(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required}


_STR = {"type": "string"}

# The registry. Order is the order presented to the model.
_TOOL_DEFS: list[_ToolDef] = [
    _ToolDef(
        Tool("read_file", "Read a text file in the project.", _obj({"path": _STR}, ["path"])),
        _read_file,
    ),
    _ToolDef(
        Tool(
            "list_dir",
            "List files and folders at a project-relative path (default project root).",
            _obj({"path": _STR}, []),
        ),
        _list_dir,
    ),
    _ToolDef(
        Tool(
            "write_file",
            "Create or overwrite a file with full content. Requires user approval.",
            _obj({"path": _STR, "content": _STR}, ["path", "content"]),
        ),
        _write_file,
    ),
    _ToolDef(
        Tool(
            "apply_patch",
            "Edit a file by replacing an exact, unique substring ('find') with 'replace'.",
            _obj({"path": _STR, "find": _STR, "replace": _STR}, ["path", "find", "replace"]),
        ),
        _apply_patch,
    ),
    _ToolDef(
        Tool(
            "run_engine",
            "Run the game in the engine and return logs + whether it ran cleanly.",
            _obj({"headless": {"type": "boolean"}, "scene": _STR}, []),
        ),
        _run_engine,
    ),
    _ToolDef(
        Tool("screenshot", "Capture a screenshot of the current scene.", _obj({"scene": _STR}, [])),
        _screenshot,
    ),
    _ToolDef(
        Tool("read_logs", "Return the logs from the most recent run_engine call.", _obj({}, [])),
        _read_logs,
    ),
    _ToolDef(
        Tool(
            "verify_game",
            "Run the game headless and check gameplay assertions (e.g. player_on_floor, "
            "player_not_falling, no_errors). Use after run_engine to confirm it ACTUALLY works.",
            _obj({"checks": {"type": "array", "items": _STR}, "scene": _STR}, []),
        ),
        _verify_game,
    ),
    _ToolDef(
        Tool(
            "list_assets",
            "List image/audio art already imported into the project (use these over placeholders).",
            _obj({}, []),
        ),
        _list_assets,
    ),
    _ToolDef(
        Tool(
            "generate_asset",
            "Generate a game asset from a text prompt (optional; may be unavailable).",
            _obj({"prompt": _STR, "kind": _STR}, ["prompt"]),
        ),
        _generate_asset,
    ),
    _ToolDef(
        Tool(
            "task_complete",
            "Call ONLY after verify_game reports all gameplay assertions PASS (not just 'no "
            "parse errors'). Ends the task.",
            _obj({"summary": _STR}, ["summary"]),
        ),
        lambda args, ctx: args.get("summary", "Done."),
        sentinel=True,
    ),
]

_BY_NAME: dict[str, _ToolDef] = {d.tool.name: d for d in _TOOL_DEFS}


def all_tools() -> list[Tool]:
    """The tool schemas to advertise to the model."""
    return [d.tool for d in _TOOL_DEFS]


def is_sentinel(name: str) -> bool:
    d = _BY_NAME.get(name)
    return bool(d and d.sentinel)


def execute(call: ToolCall, ctx: ToolContext) -> str:
    """Dispatch one tool call, returning the string result fed back to the model."""
    definition = _BY_NAME.get(call.name)
    if definition is None:
        return f"Unknown tool '{call.name}'. Available: {', '.join(_BY_NAME)}."
    try:
        return definition.handler(call.arguments, ctx)
    except ToolError as exc:
        return f"Error: {exc}"
    except KeyError as exc:
        return f"Missing required argument {exc} for tool '{call.name}'."
    except Exception as exc:  # noqa: BLE001 — surface failures to the model, don't crash the loop
        return f"Tool '{call.name}' raised: {exc}"
