"""Playsmith web UI — a chat-style frontend + interactive panel over the same core.

A thin FastAPI layer (no new game/engine logic): a WebSocket streams the agent loop live
(like a chat), and REST endpoints list projects/skills, browse files, and export+serve the game
for in-browser play. Everything runs the exact same `studio`/agent the CLI uses.

Run: `playsmith web` (or `uvicorn playsmith.web.server:app`).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from playsmith.config import load_config
from playsmith.engines import ExportTarget, GodotAdapter
from playsmith.skills import SkillLoader
from playsmith.studio import edit_game, new_game, read_manifest

_STATIC = Path(__file__).parent / "static"
_ASSET_EXTS = {".gd", ".tscn", ".godot", ".cfg", ".json", ".txt", ".md", ".import"}

app = FastAPI(title="Playsmith")


def _workspace() -> Path:
    return load_config().workspace_dir.expanduser()


def _projects() -> list[dict]:
    ws = _workspace()
    if not ws.is_dir():
        return []
    out = []
    for p in sorted(ws.iterdir(), key=lambda d: -d.stat().st_mtime if d.is_dir() else 0):
        if p.is_dir() and p.name != "_playsmith_engine_check" and (p / "project.godot").exists():
            manifest = read_manifest(p) or {}
            out.append(
                {
                    "name": p.name,
                    "skill": manifest.get("skill"),
                    "prompt": manifest.get("prompt"),
                    "has_build": (p / "build" / "index.html").exists(),
                }
            )
    return out


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((_STATIC / "index.html").read_text())


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


@app.get("/api/skills")
def api_skills() -> JSONResponse:
    skills = SkillLoader().discover()
    return JSONResponse(
        [
            {"name": s.name, "source": s.source, "trusted": s.trusted, "description": s.description}
            for s in skills
        ]
    )


@app.get("/api/projects")
def api_projects() -> JSONResponse:
    return JSONResponse(_projects())


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


@app.post("/api/projects/{name}/export")
def api_export(name: str) -> JSONResponse:
    cfg = load_config()
    root = (_workspace() / name).resolve()
    if not (root / "project.godot").exists():
        return JSONResponse({"error": "no such project"}, status_code=404)
    adapter = GodotAdapter(root, binary=cfg.engine.godot.binary)
    out = root / "build" / "index.html"
    result = adapter.export(ExportTarget.WEB, str(out))
    if out.exists() and result.returncode == 0:
        return JSONResponse({"ok": True, "play": f"/play/{name}/index.html"})
    return JSONResponse({"ok": False, "logs": result.logs[-1500:]}, status_code=200)


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
