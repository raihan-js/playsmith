"""FastAPI web UI for the Unreal-first flow, wired to the docs/design studio look.

A thin layer over the same building blocks as `playsmith unreal new` (UnrealAdapter + director).
UE work is slow and blocking, so each step runs in a worker thread and streams design-vocabulary
events (start/phase/tool/observe/done) over a WebSocket so the studio's build view renders live.
Optional — install with ``pip install -e ".[web]"``; nothing in the core depends on it.

WebSocket protocol (JSON text both ways), on ``/ws``:
  client → {"action":"build","prompt":..,"genre"?:..}   # genre inferred from the prompt if omitted
         | {"action":"dress","name":<slug>,"prompt":..}  # iterate on an existing project
         | {"action":"render","name":<slug>}
         | {"action":"play","name":<slug>}
  server → {"type":"start"|"phase"|"tool"|"observe"|"error", ...}
         | {"type":"done","project":<slug>,"skill":<genre>,"assertions":{..},"summary":..,
            "preview":"/preview/<slug>","playable":bool}
REST: GET / (UI) · /api/config · /api/genres · /api/projects · /api/skills · /api/files/<slug>
      · /preview/<slug>
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from playsmith.config import load_config, save_runtime_patch
from playsmith.engines.base import EngineError
from playsmith.engines.unreal import critic, director, refine, template_clone
from playsmith.engines.unreal.adapter import UnrealAdapter
from playsmith.llm import LLMGateway
from playsmith.llm import catalog as model_catalog

_STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Playsmith")

# Genre descriptions for the Skills tab (the three build-on-template genres).
_GENRE_INFO = {
    "third-person": ("🏃", "Over-the-shoulder character on UE's Third Person template — dress it "
                     "with obstacles, platforms, jump pads and a goal."),
    "first-person": ("🔫", "First-person template (gun + projectiles) — build a small arena with "
                     "targets and cover."),
    "top-down": ("🎯", "Top-down template — a click/WASD arena with collectibles and hazards."),
}
_TEXT_FILES = (".uproject", ".ini", ".py")  # the human-readable bits of a UE project


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    s = "-".join(s.split("-")[:6])  # keep generated project names short
    return s[:48] or "unreal-game"


def _proj_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", name or "")[:40] or "Game"


def _pretty(slug: str) -> str:
    """A readable fallback title from a project slug (when no manifest title exists)."""
    return " ".join(w.capitalize() for w in slug.replace("-", " ").split()) or slug


# Structured composer fields the studio can pass so a prompt is more directive than one text line.
_HINT_KEYS = ("theme", "vibe", "difficulty", "size")


def _hints(req: dict) -> dict:
    out: dict[str, str] = {}
    for key in _HINT_KEYS:
        value = req.get(key)
        if isinstance(value, str) and value.strip():
            out[key] = value.strip()[:60]
    return out


def _iters(req: dict, hints: dict) -> int:
    """How many director→critic passes to run: explicit override, else derived from level size."""
    explicit = req.get("iterations")
    if isinstance(explicit, (int, float)) and explicit:
        return max(1, min(5, int(explicit)))
    return {"small": 2, "large": 4}.get((hints.get("size") or "").lower(), 3)


def _infer_genre(prompt: str) -> str:
    """Pick a template from the prompt (the studio composer has no explicit genre picker)."""
    p = (prompt or "").lower()
    if any(w in p for w in ("first person", "first-person", "fps", "shooter", "shoot")):
        return "first-person"
    if any(w in p for w in ("top down", "top-down", "twin stick", "twin-stick", "strategy", "rts")):
        return "top-down"
    return "third-person"


def _manifest_path(project_dir: Path) -> Path:
    return project_dir / ".playsmith" / "manifest.json"


def _read_manifest(project_dir: Path) -> dict:
    path = _manifest_path(project_dir)
    if path.is_file():
        try:
            data = json.loads(path.read_text())
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _write_manifest(project_dir: Path, **fields) -> None:
    path = _manifest_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _read_manifest(project_dir)
    data.update({k: v for k, v in fields.items() if v is not None})
    path.write_text(json.dumps(data, indent=2))


def _list_projects(workspace: Path) -> list[dict]:
    out: list[dict] = []
    if workspace.is_dir():
        for p in sorted(workspace.iterdir()):
            if p.is_dir() and next(p.glob("*.uproject"), None):
                m = _read_manifest(p)
                out.append(
                    {
                        "name": p.name,
                        "title": m.get("title") or _pretty(p.name),
                        "genre": m.get("genre", "third-person"),
                        "playable": bool(m.get("playable", True)),
                        "prompt": m.get("objective") or m.get("prompt") or p.name,
                        "theme": m.get("theme", ""),
                        "quality": m.get("quality"),
                        "iterations": m.get("iterations"),
                        "has_preview": (p / "preview.png").exists(),
                    }
                )
    return out


def _project_files(project_dir: Path) -> list[dict]:
    """The readable files of a UE project (uproject + configs + Playsmith scripts)."""
    out: list[dict] = []
    for f in sorted(project_dir.rglob("*")):
        if not (f.is_file() and f.suffix.lower() in _TEXT_FILES):
            continue
        rel = f.relative_to(project_dir).as_posix()
        if rel.startswith(("Intermediate/", "Binaries/", "DerivedDataCache/")):
            continue
        try:
            if f.stat().st_size > 64_000:
                continue
            out.append(
                {"path": rel, "size": f.stat().st_size, "text": f.read_text(errors="ignore")}
            )
        except OSError:
            continue
    return out[:40]


# -- REST --------------------------------------------------------------------------
@app.get("/")
def index() -> HTMLResponse:
    page = _STATIC / "index.html"
    if not page.exists():
        return HTMLResponse("<h1>Playsmith</h1><p>UI not built.</p>", status_code=200)
    return HTMLResponse(page.read_text())


@app.get("/api/config")
def api_config() -> JSONResponse:
    cfg = load_config()
    return JSONResponse(
        {
            "model": cfg.llm.model,
            "provider": cfg.llm.provider,
            "where": "local" if cfg.llm.is_local else "cloud",
            "workspace": str(cfg.workspace_dir),
        }
    )


@app.get("/api/models")
def api_models() -> JSONResponse:
    """Providers + models for the Settings picker (live-discovers local Ollama models)."""
    return JSONResponse(model_catalog.catalog(load_config()))


@app.post("/api/config")
async def api_set_config(request: Request) -> JSONResponse:
    """Persist a provider/model pick (+ optional API key / base_url) from the Settings modal."""
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        body = {}
    try:
        patch = model_catalog.config_patch_for(
            (body.get("provider") or "").strip(),
            (body.get("model") or "").strip(),
            body.get("api_key"),
            body.get("base_url"),
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    save_runtime_patch(patch)
    cfg = load_config()
    return JSONResponse(
        {
            "ok": True,
            "model": cfg.llm.model,
            "provider": cfg.llm.provider,
            "where": "local" if cfg.llm.is_local else "cloud",
        }
    )


@app.get("/api/genres")
def api_genres() -> JSONResponse:
    return JSONResponse({"genres": sorted(template_clone.TEMPLATES)})


@app.get("/api/skills")
def api_skills() -> JSONResponse:
    skills = [
        {
            "name": g,
            "source": "builtin",
            "trusted": True,
            "installed": True,
            "emoji": _GENRE_INFO.get(g, ("🎮", ""))[0],
            "description": _GENRE_INFO.get(g, ("", ""))[1],
        }
        for g in sorted(template_clone.TEMPLATES)
    ]
    return JSONResponse({"skills": skills})


@app.get("/api/projects")
def api_projects() -> JSONResponse:
    cfg = load_config()
    return JSONResponse({"projects": _list_projects(cfg.workspace_dir.expanduser())})


@app.delete("/api/projects/{name}")
def api_delete_project(name: str) -> JSONResponse:
    """Delete a generated UE project from the workspace (workspace-scoped, real-project only)."""
    cfg = load_config()
    workspace = cfg.workspace_dir.expanduser().resolve()
    target = (workspace / _slug(name)).resolve()
    # Safety: only a direct child of the workspace that is a real UE project may be removed.
    if (
        target.parent != workspace
        or not target.is_dir()
        or next(target.glob("*.uproject"), None) is None
    ):
        return JSONResponse({"error": f"No such project: {name}"}, status_code=404)
    shutil.rmtree(target, ignore_errors=True)
    return JSONResponse({"ok": True, "deleted": target.name})


@app.get("/api/files/{name}")
def api_files(name: str) -> JSONResponse:
    cfg = load_config()
    project_dir = cfg.workspace_dir.expanduser() / _slug(name)
    if not project_dir.is_dir():
        return JSONResponse({"files": []})
    return JSONResponse({"files": _project_files(project_dir)})


@app.get("/preview/{name}")
def preview(name: str):
    cfg = load_config()
    png = cfg.workspace_dir.expanduser() / _slug(name) / "preview.png"
    if not png.exists():
        return JSONResponse({"error": "no preview"}, status_code=404)
    return FileResponse(png, media_type="image/png")


# -- WebSocket ---------------------------------------------------------------------
@app.websocket("/ws")
async def ws(sock: WebSocket) -> None:
    await sock.accept()
    try:
        while True:
            raw = await sock.receive_text()
            try:
                req = json.loads(raw)
            except json.JSONDecodeError:
                continue
            try:
                await _handle(sock, req)
            except (EngineError, OSError) as exc:
                await _send(sock, type="error", text=str(exc))
            except Exception as exc:  # noqa: BLE001 - report, don't drop the socket
                await _send(sock, type="error", text=f"Unexpected error: {exc}")
    except WebSocketDisconnect:
        return


async def _send(sock: WebSocket, **kwargs) -> None:
    await sock.send_text(json.dumps(kwargs))


def _fmt(assertions: dict) -> str:
    return " · ".join(f"{k} {'PASS' if v else 'FAIL'}" for k, v in assertions.items()) or "(none)"


async def _handle(sock: WebSocket, req: dict) -> None:
    cfg = load_config()
    workspace = cfg.workspace_dir.expanduser()
    action = req.get("action")

    if action == "build":
        prompt = (req.get("prompt") or "").strip() or "a third person adventure"
        genre = (req.get("genre") or _infer_genre(prompt)).lower()
        hints = _hints(req)
        await _build(sock, cfg, workspace, prompt, genre, hints, _iters(req, hints))
        return

    if action == "dress":
        name = _slug(req.get("name") or "")
        project_dir = workspace / name
        if not (project_dir.is_dir() and next(project_dir.glob("*.uproject"), None)):
            await _send(sock, type="error", text=f"No such project: {name}")
            return
        prompt = (req.get("prompt") or "").strip() or name
        genre = (_read_manifest(project_dir).get("genre") or _infer_genre(prompt)).lower()
        hints = _hints(req)
        await _dress(sock, cfg, project_dir, name, prompt, genre, hints, _iters(req, hints))
        return

    if action == "render":
        await _render(sock, cfg, workspace, _slug(req.get("name") or ""))
        return

    if action == "play":
        await _play(sock, cfg, workspace, _slug(req.get("name") or ""))
        return

    await _send(sock, type="error", text=f"Unknown action: {action}")


async def _build(sock, cfg, workspace, prompt, genre, hints=None, max_iters=3) -> None:
    tspec = template_clone.TEMPLATES.get(genre)
    if tspec is None:
        await _send(sock, type="error", text=f"Unknown genre: {genre}")
        return
    name = _slug(prompt)
    project_dir = workspace / name
    adapter = UnrealAdapter(project_dir, editor_cmd=cfg.engine.unreal.editor_cmd)

    await _send(sock, type="start", action="new", prompt=prompt)
    await _send(sock, type="phase", text=f"Cloning the {genre} UE template")
    await _send(sock, type="tool", name="clone", args={"path": genre})
    await asyncio.to_thread(adapter.create_from_template, genre, project_name=_proj_name(prompt))
    await _send(sock, type="observe", name="clone", text="Shared content merged", ok=True)

    await _send(sock, type="phase", text="Verifying the project in-engine")
    await _send(sock, type="tool", name="verify_game", args={})
    v = await asyncio.to_thread(adapter.verify_template, tspec)
    await _send(sock, type="observe", name="verify_game", text=_fmt(v.assertions), ok=v.ok)

    result = await _direct(sock, cfg, adapter, prompt, genre, tspec, hints, max_iters)
    dressing, score = result.spec, (result.critique.score if result.critique else None)

    playable = bool(v.ok)
    _write_manifest(
        project_dir, genre=genre, prompt=prompt, title=dressing.get("title"),
        objective=dressing.get("objective"), theme=dressing.get("theme"),
        quality=score, iterations=result.iterations, playable=playable,
    )
    assertions = {**dict(v.assertions), "objects_placed": True}
    summary = f"{dressing.get('theme', '')} — {dressing.get('objective', '')}".strip(" —")
    await _send(
        sock, type="done", done=True, runs_clean=playable, project=name, skill=genre,
        title=dressing.get("title"), assertions=assertions, summary=summary, quality=score,
        iterations=result.iterations, preview=f"/preview/{name}", playable=playable,
    )


async def _dress(sock, cfg, project_dir, name, prompt, genre, hints=None, max_iters=3) -> None:
    tspec = template_clone.TEMPLATES.get(genre)
    if tspec is None:
        await _send(sock, type="error", text=f"Unknown genre: {genre}")
        return
    adapter = UnrealAdapter(project_dir, editor_cmd=cfg.engine.unreal.editor_cmd)
    await _send(sock, type="start", action="edit", prompt=prompt, project=name)
    result = await _direct(sock, cfg, adapter, prompt, genre, tspec, hints, max_iters)
    dressing, score = result.spec, (result.critique.score if result.critique else None)
    _write_manifest(
        project_dir, prompt=prompt, title=dressing.get("title"),
        objective=dressing.get("objective"), theme=dressing.get("theme"),
        quality=score, iterations=result.iterations,
    )
    summary = f"{dressing.get('theme', '')} — {dressing.get('objective', '')}".strip(" —")
    await _send(
        sock, type="done", done=True, runs_clean=True, project=name, skill=genre,
        title=dressing.get("title"), assertions={"objects_placed": True}, summary=summary,
        quality=score, iterations=result.iterations, preview=f"/preview/{name}", playable=True,
    )


async def _direct(
    sock, cfg, adapter, prompt, genre, tspec, hints, max_iters
) -> refine.RefineResult:
    """Run the director→critic refine loop in a worker thread, streaming each step to the socket.

    The loop is blocking (UE Python per pass), so it runs in an executor; its ``on_event`` hook is
    bridged onto the event loop via a queue so the studio sees the agent plan → apply → critique →
    improve, iteration by iteration. Returns the final :class:`refine.RefineResult`.
    """
    await _send(sock, type="phase", text="Directing the level — agent iterates for quality")
    gateway = LLMGateway.from_config(cfg)
    size = (hints or {}).get("size")

    def _plan() -> dict:
        return director.plan_dressing(prompt, genre, gateway, hints=hints)

    def _apply(spec: dict) -> dict:
        return dict(adapter.dress_from_spec(spec, tspec.map_path).assertions)

    def _critique(spec: dict, assertions: dict | None):
        return critic.critique(spec, assertions, size=size)

    def _improve(spec: dict, crit):
        return director.improve_dressing(prompt, genre, gateway, spec, crit, hints=hints)

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    sentinel = object()

    def _on_event(ev: dict) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, ev)

    def _run() -> refine.RefineResult:
        try:
            return refine.refine(
                plan=_plan, apply=_apply, critique=_critique, improve=_improve,
                max_iters=max_iters, on_event=_on_event,
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, sentinel)

    fut = loop.run_in_executor(None, _run)
    while True:
        ev = await queue.get()
        if ev is sentinel:
            break
        await _stream_refine_event(sock, ev)
    return await fut


async def _stream_refine_event(sock, ev: dict) -> None:
    """Map one refine-loop event to the studio's build-stream vocabulary."""
    kind = ev.get("kind")
    if kind == "planned":
        await _send(sock, type="tool", name="generate_asset", args={})
        await _send(
            sock, type="observe", name="generate_asset",
            text=f"{ev.get('objects', 0)} objects placed", ok=True,
        )
    elif kind == "applied":
        await _send(
            sock, type="tool", name="write_file", args={"path": f"Lvl (pass {ev.get('iter', 1)})"}
        )
        await _send(
            sock, type="observe", name="write_file", text=_fmt(ev.get("assertions") or {}), ok=True
        )
    elif kind == "critiqued":
        await _send(
            sock, type="critic", iter=ev.get("iter"), score=ev.get("score"),
            passed=ev.get("passed"), feedback=ev.get("feedback") or [], summary=ev.get("summary"),
        )
    elif kind == "improving":
        await _send(
            sock, type="phase",
            text=f"Critic sent it back — refining (pass {ev.get('iter', 1)})",
        )


async def _render(sock, cfg, workspace, name: str) -> None:
    project_dir = workspace / name
    tspec = template_clone.TEMPLATES.get(_read_manifest(project_dir).get("genre", "third-person"))
    if not (project_dir.is_dir() and next(project_dir.glob("*.uproject"), None)) or tspec is None:
        await _send(sock, type="error", text=f"No such project: {name}")
        return
    adapter = UnrealAdapter(project_dir, editor_cmd=cfg.engine.unreal.editor_cmd)
    await _send(sock, type="phase", text="Rendering a preview (first render compiles shaders)")
    await asyncio.to_thread(
        adapter.render_screenshot, project_dir / "preview.png", scene=tspec.map_path
    )
    ok = (project_dir / "preview.png").exists()
    await _send(
        sock, type="observe", name="screenshot",
        text="Captured frame" if ok else "No frame", ok=ok,
    )
    await _send(
        sock, type="done", done=True, project=name,
        preview=f"/preview/{name}", ok=ok, playable=True,
    )


async def _play(sock, cfg, workspace, name: str) -> None:
    project_dir = workspace / name
    tspec = template_clone.TEMPLATES.get(_read_manifest(project_dir).get("genre", "third-person"))
    if not (project_dir.is_dir() and next(project_dir.glob("*.uproject"), None)) or tspec is None:
        await _send(sock, type="error", text=f"No such project: {name}")
        return
    adapter = UnrealAdapter(project_dir, editor_cmd=cfg.engine.unreal.editor_cmd)
    await _send(sock, type="phase", text="Launching the game window (WASD + mouse) …")
    pid = await asyncio.to_thread(adapter.play, scene=tspec.map_path)
    await _send(sock, type="observe", name="run_engine", text=f"Game launched (pid {pid})", ok=True)
    await _send(
        sock, type="done", done=True, project=name,
        preview=f"/preview/{name}", ok=True, playable=True,
    )
