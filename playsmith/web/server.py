"""Playsmith web UI — a chat-style frontend + interactive panel over the same core.

A thin FastAPI layer (no new game/engine logic): a WebSocket streams the agent loop live
(like a chat), and REST endpoints list projects/skills, browse files, manage models, generate art,
and export the game — for in-browser play OR a real native desktop build. Everything runs the exact
same `studio`/agent the CLI uses.

Run: `playsmith web` (or `uvicorn playsmith.web.server:app`).
"""

from __future__ import annotations

import asyncio
import zipfile
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from playsmith.assets import get_asset_generator
from playsmith.config import load_config, save_runtime_patch
from playsmith.engines import ExportTarget, GodotAdapter
from playsmith.llm import catalog as model_catalog
from playsmith.skills import SkillLoader
from playsmith.studio import edit_game, new_game, read_manifest

_STATIC = Path(__file__).parent / "static"
_ASSET_EXTS = {".gd", ".tscn", ".godot", ".cfg", ".json", ".txt", ".md", ".import"}

# skill name -> friendly genre label shown on project cards.
_GENRE = {
    "2d-platformer": "Platformer",
    "endless-runner": "Runner",
    "space-shooter": "Shooter",
    "top-down-roguelike": "Roguelike",
    "match-3-puzzle": "Puzzle",
    "racing-kart": "Racing",
}

# Native desktop export targets (the "real game" the user opens on their PC) + web.
_TARGETS = {
    "web": ExportTarget.WEB,
    "linux": ExportTarget.LINUX,
    "windows": ExportTarget.WINDOWS,
    "mac": ExportTarget.MACOS,
}
_NATIVE_EXT = {"linux": ".x86_64", "windows": ".exe", "mac": ".zip"}

app = FastAPI(title="Playsmith")


def _workspace() -> Path:
    return load_config().workspace_dir.expanduser()


def _genre_for(skill: str | None) -> str:
    if not skill:
        return "Game"
    return _GENRE.get(skill, skill.replace("-", " ").title())


def _thumb_path(project: Path) -> Path | None:
    """The best available thumbnail: a captured frame, else the generated background."""
    for candidate in ("thumbnail.png", "assets/background.png", "assets/player.png"):
        p = project / candidate
        if p.exists():
            return p
    return None


def _projects() -> list[dict]:
    ws = _workspace()
    if not ws.is_dir():
        return []
    out = []
    for p in sorted(ws.iterdir(), key=lambda d: -d.stat().st_mtime if d.is_dir() else 0):
        if p.is_dir() and p.name != "_playsmith_engine_check" and (p / "project.godot").exists():
            manifest = read_manifest(p) or {}
            has_build = (p / "build" / "index.html").exists()
            skill = manifest.get("skill")
            # Deterministic scaffold always runs; playable unless verify said otherwise.
            playable = bool(manifest.get("runs_clean", True))
            out.append(
                {
                    "name": p.name,
                    "skill": skill,
                    "genre": _genre_for(skill),
                    "prompt": manifest.get("prompt"),
                    "has_build": has_build,
                    "playable": playable,
                    "has_thumb": _thumb_path(p) is not None,
                }
            )
    return out


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((_STATIC / "index.html").read_text())


# ---------------------------------------------------------------- config + models
@app.get("/api/config")
def api_config() -> JSONResponse:
    cfg = load_config()
    return JSONResponse(
        {
            "model": cfg.llm.model,
            "provider": cfg.llm.provider,
            "where": "local" if cfg.llm.is_local else "cloud",
            "workspace": str(cfg.workspace_dir),
            "assets_enabled": cfg.assets.enabled,
        }
    )


@app.post("/api/config")
async def api_set_config(request: Request) -> JSONResponse:
    """Persist a provider/model selection (+ optional API key/base_url) from Settings."""
    body = await request.json()
    provider = (body.get("provider") or "").strip()
    model = (body.get("model") or "").strip()
    if not provider or not model:
        return JSONResponse({"error": "provider and model are required"}, status_code=400)
    patch = model_catalog.config_patch_for(
        provider, model, body.get("api_key"), body.get("base_url")
    )
    save_runtime_patch(patch)
    cfg = load_config()
    return JSONResponse(
        {"ok": True, "model": cfg.llm.model, "provider": cfg.llm.provider,
         "where": "local" if cfg.llm.is_local else "cloud"}
    )


@app.get("/api/models")
def api_models() -> JSONResponse:
    """Discover reachable providers + their models for the Settings picker."""
    return JSONResponse(model_catalog.catalog(load_config()))


@app.websocket("/ws/pull")
async def ws_pull(websocket: WebSocket) -> None:
    """Download a local (Ollama) model, streaming progress to the Settings UI."""
    await websocket.accept()
    try:
        msg = await websocket.receive_json()
        model = (msg.get("model") or "").strip()
        if not model:
            await websocket.send_json({"status": "error", "error": "no model", "done": True})
            return
        base = model_catalog.ollama_base(load_config())
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def work() -> None:
            for ev in model_catalog.pull_ollama(base, model):
                loop.call_soon_threadsafe(queue.put_nowait, ev)
            loop.call_soon_threadsafe(queue.put_nowait, {"_end": True})

        task = asyncio.create_task(asyncio.to_thread(work))
        while True:
            ev = await queue.get()
            if ev.get("_end"):
                break
            await websocket.send_json(ev)
        await task
        await websocket.send_json({"status": "ready", "done": True, "installed": True})
    except WebSocketDisconnect:
        return


# ---------------------------------------------------------------- skills + projects
@app.get("/api/skills")
def api_skills() -> JSONResponse:
    skills = SkillLoader().discover()
    return JSONResponse(
        [
            {
                "name": s.name,
                "source": s.source,
                "trusted": s.trusted,
                "description": s.description,
                "genre": _genre_for(s.name),
            }
            for s in skills
        ]
    )


@app.get("/api/projects")
def api_projects() -> JSONResponse:
    return JSONResponse(_projects())


@app.delete("/api/projects/{name}")
def api_delete_project(name: str) -> JSONResponse:
    """Permanently delete a generated game folder (only real projects under the workspace)."""
    import shutil

    ws = _workspace().resolve()
    root = (ws / name).resolve()
    if ws not in root.parents or not root.is_dir() or not (root / "project.godot").exists():
        return JSONResponse({"error": "no such project"}, status_code=404)
    shutil.rmtree(root)
    return JSONResponse({"ok": True, "deleted": name})


@app.get("/api/projects/{name}/thumb")
def api_thumb(name: str) -> Response:
    root = (_workspace() / name).resolve()
    if _workspace().resolve() not in root.parents:
        return Response("not found", status_code=404)
    thumb = _thumb_path(root)
    if thumb is None:
        return Response("no thumb", status_code=404)
    return FileResponse(thumb)


@app.get("/api/projects/{name}/files")
def api_files(name: str) -> JSONResponse:
    root = (_workspace() / name).resolve()
    if _workspace().resolve() not in root.parents or not root.is_dir():
        return JSONResponse({"error": "no such project"}, status_code=404)
    files = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and not any(part.startswith(".") for part in p.relative_to(root).parts):
            rel = p.relative_to(root).as_posix()
            text = ""
            if p.suffix.lower() in _ASSET_EXTS and p.stat().st_size < 60_000:
                text = p.read_text(errors="replace")
            files.append({"path": rel, "size": p.stat().st_size, "text": text})
    return JSONResponse({"name": name, "files": files})


@app.post("/api/projects/{name}/asset")
async def api_gen_asset(name: str, request: Request) -> JSONResponse:
    """Generate a sprite/background/tileset and import it into the project."""
    cfg = load_config()
    root = (_workspace() / name).resolve()
    if not (root / "project.godot").exists():
        return JSONResponse({"error": "no such project"}, status_code=404)
    body = await request.json()
    prompt = (body.get("prompt") or "").strip()
    kind = (body.get("kind") or "sprite").strip()
    if not prompt:
        return JSONResponse({"error": "prompt required"}, status_code=400)
    gen = get_asset_generator(cfg)
    if gen is None or not gen.available():
        return JSONResponse(
            {"error": "Asset generation is off. Set an OpenAI key in Settings to enable art."},
            status_code=400,
        )
    # Map to a slot game.gd auto-applies so generated art shows up in-game immediately.
    fname = {"background": "background.png", "sprite": "player.png"}.get(
        kind, _safe_asset_name(prompt)
    )
    out = root / "assets" / fname
    try:
        await asyncio.to_thread(gen.image, prompt, kind, str(out))
        adapter = GodotAdapter(root, binary=cfg.engine.godot.binary)
        await asyncio.to_thread(adapter.import_assets)
    except Exception as exc:  # noqa: BLE001 - report generation failure to the UI
        return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, status_code=200)
    return JSONResponse({"ok": True, "name": fname, "kind": kind,
                         "url": f"/api/projects/{name}/asset-file/{fname}"})


@app.get("/api/projects/{name}/asset-file/{fname}")
def api_asset_file(name: str, fname: str) -> Response:
    root = (_workspace() / name / "assets").resolve()
    target = (root / fname).resolve()
    if root not in target.parents or not target.is_file():
        return Response("not found", status_code=404)
    return FileResponse(target)


# ---------------------------------------------------------------- export (web + native)
@app.post("/api/projects/{name}/export")
async def api_export(name: str, request: Request) -> JSONResponse:
    """Export the game. ``target=web`` returns a play URL; native targets return a download URL."""
    cfg = load_config()
    root = (_workspace() / name).resolve()
    if not (root / "project.godot").exists():
        return JSONResponse({"error": "no such project"}, status_code=404)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 - body is optional; default to web
        body = {}
    target = (body.get("target") or "web").lower()
    if target not in _TARGETS:
        return JSONResponse({"error": f"unknown target {target}"}, status_code=400)
    adapter = GodotAdapter(root, binary=cfg.engine.godot.binary)

    if target == "web":
        out = root / "build" / "index.html"
        result = await asyncio.to_thread(adapter.export, ExportTarget.WEB, str(out))
        if out.exists() and result.returncode == 0:
            return JSONResponse({"ok": True, "target": "web", "play": f"/play/{name}/index.html"})
        return JSONResponse({"ok": False, "logs": result.logs[-1800:]}, status_code=200)

    # Native desktop build -> export into build/<target>/, then zip the folder for download.
    out_dir = root / "build" / target
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{name}{_NATIVE_EXT[target]}"
    result = await asyncio.to_thread(adapter.export, _TARGETS[target], str(out_file))
    produced = any(out_dir.iterdir())
    if not produced or result.returncode != 0:
        return JSONResponse(
            {"ok": False, "target": target,
             "hint": "Native export needs Godot export templates installed for this platform.",
             "logs": result.logs[-1800:]},
            status_code=200,
        )
    zip_path = root / "build" / f"{name}-{target}.zip"
    await asyncio.to_thread(_zip_dir, out_dir, zip_path)
    return JSONResponse(
        {"ok": True, "target": target, "download": f"/api/projects/{name}/download/{target}",
         "filename": zip_path.name}
    )


def _zip_dir(src_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(src_dir.rglob("*")):
            if f.is_file():
                zf.write(f, f.relative_to(src_dir.parent))


@app.get("/api/projects/{name}/download/{target}")
def api_download(name: str, target: str) -> Response:
    root = (_workspace() / name).resolve()
    zip_path = (root / "build" / f"{name}-{target}.zip").resolve()
    if root not in zip_path.parents or not zip_path.is_file():
        return Response("not found", status_code=404)
    return FileResponse(zip_path, filename=zip_path.name, media_type="application/zip")


def _safe_asset_name(prompt: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", prompt.lower()).strip("-")[:20] or "asset"
    return f"{slug}.png"


# Cross-origin isolation headers so Godot's threaded WASM (SharedArrayBuffer) runs in the iframe.
_COOP = {
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Embedder-Policy": "require-corp",
}


@app.get("/play/{name}/{path:path}")
def play(name: str, path: str) -> Response:
    build = (_workspace() / name / "build").resolve()
    target = (build / path).resolve()
    if build not in target.parents and target != build or not target.is_file():
        return Response("not found", status_code=404)
    return FileResponse(target, headers=_COOP)


# ---------------------------------------------------------------- live build stream
async def _stream_build(
    websocket: WebSocket, action: str, prompt: str, project: str | None
) -> None:
    """Run new_game/edit_game in a worker thread, streaming its events over the WebSocket."""
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def sink(ev: dict) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, ev)

    def work() -> None:
        try:
            if action == "edit":
                target = str(_workspace() / project) if project else None
                edit_game(
                    prompt, project_dir=target, auto_approve=True, verbose=False, on_event=sink
                )
            else:
                new_game(prompt, auto_approve=True, verbose=False, on_event=sink)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            sink({"type": "error", "text": f"{type(exc).__name__}: {exc}"})
        finally:
            sink({"type": "_end"})

    await websocket.send_json({"type": "start", "action": action, "prompt": prompt})
    task = asyncio.create_task(asyncio.to_thread(work))
    while True:
        ev = await queue.get()
        if ev.get("type") == "_end":
            break
        await websocket.send_json(ev)
    await task


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            msg = await websocket.receive_json()
            prompt = (msg.get("prompt") or "").strip()
            if not prompt:
                await websocket.send_json({"type": "error", "text": "empty prompt"})
                continue
            await _stream_build(websocket, msg.get("action", "new"), prompt, msg.get("project"))
    except WebSocketDisconnect:
        return


app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")
