"""FastAPI web UI for the Unreal-first flow: prompt → clone → dress → render, streamed live.

A thin front end over the same building blocks as `playsmith unreal new`:
:class:`~playsmith.engines.unreal.adapter.UnrealAdapter` + the director. UE work is slow and
blocking, so each step runs in a worker thread and emits coarse progress events over a WebSocket.
Optional — install with ``pip install -e ".[web]"``; nothing in the core depends on it.

WebSocket protocol (JSON text both ways), on ``/ws``:
  client → ``{"action":"build","prompt":..,"genre":..,"dress":bool}``
         | ``{"action":"render","name":<slug>,"genre":..}``
  server → ``{"type":"log","text":..}`` (progress)
         | ``{"type":"done","project":<slug>,"preview":"/preview/<slug>","ok":bool}``
         | ``{"type":"error","text":..}``
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from playsmith.config import load_config
from playsmith.engines.base import EngineError
from playsmith.engines.unreal import director, template_clone
from playsmith.engines.unreal.adapter import UnrealAdapter
from playsmith.llm import LLMGateway

_STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Playsmith")


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-") or "unreal-game"


def _proj_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", name or "")[:40] or "Game"


def _list_projects(workspace: Path) -> list[dict]:
    out: list[dict] = []
    if workspace.is_dir():
        for p in sorted(workspace.iterdir()):
            if p.is_dir() and next(p.glob("*.uproject"), None):
                out.append({"name": p.name, "has_preview": (p / "preview.png").exists()})
    return out


@app.get("/")
def index() -> HTMLResponse:
    page = _STATIC / "index.html"
    if not page.exists():
        return HTMLResponse("<h1>Playsmith</h1><p>UI not built.</p>", status_code=200)
    return HTMLResponse(page.read_text())


@app.get("/api/projects")
def api_projects() -> JSONResponse:
    cfg = load_config()
    return JSONResponse({"projects": _list_projects(cfg.workspace_dir.expanduser())})


@app.get("/api/genres")
def api_genres() -> JSONResponse:
    return JSONResponse({"genres": sorted(template_clone.TEMPLATES)})


@app.get("/preview/{name}")
def preview(name: str):
    cfg = load_config()
    png = cfg.workspace_dir.expanduser() / _slug(name) / "preview.png"
    if not png.exists():
        return JSONResponse({"error": "no preview"}, status_code=404)
    return FileResponse(png, media_type="image/png")


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


async def _handle(sock: WebSocket, req: dict) -> None:
    cfg = load_config()
    workspace = cfg.workspace_dir.expanduser()
    action = req.get("action")
    genre = (req.get("genre") or "third-person").lower()
    tspec = template_clone.TEMPLATES.get(genre)
    if tspec is None:
        await _send(sock, type="error", text=f"Unknown genre: {genre}")
        return

    if action == "build":
        prompt = (req.get("prompt") or "").strip() or "a third person adventure"
        name = _slug(prompt)
        project_dir = workspace / name
        adapter = UnrealAdapter(project_dir, editor_cmd=cfg.engine.unreal.editor_cmd)

        await _send(sock, type="log", text=f"Cloning the {genre} UE template (large copy) …")
        await asyncio.to_thread(
            adapter.create_from_template, genre, project_name=_proj_name(prompt)
        )
        await _send(sock, type="log", text="Verifying the cloned project in-engine …")
        v = await asyncio.to_thread(adapter.verify_template, tspec)
        await _send(sock, type="log", text=f"Verify: {_fmt(v.assertions)}")

        if req.get("dress", True):
            await _send(sock, type="log", text="Directing the level from your prompt …")
            gateway = LLMGateway.from_config(cfg)
            dressing = await asyncio.to_thread(director.plan_dressing, prompt, genre, gateway)
            obj = dressing.get("objective", "")
            await _send(
                sock,
                type="log",
                text=f"Theme: {dressing['theme']} · {len(dressing['placements'])} objects · {obj}",
            )
            d = await asyncio.to_thread(adapter.dress_from_spec, dressing, tspec.map_path)
            await _send(sock, type="log", text=f"Dressed: {_fmt(d.assertions)}")

        await _send(sock, type="log", text="✓ Built. Render a preview, or open it in the editor.")
        await _send(sock, type="done", project=name, preview=f"/preview/{name}", ok=True)
        return

    if action == "render":
        name = _slug(req.get("name") or "")
        project_dir = workspace / name
        if not (project_dir.is_dir() and next(project_dir.glob("*.uproject"), None)):
            await _send(sock, type="error", text=f"No such project: {name}")
            return
        adapter = UnrealAdapter(project_dir, editor_cmd=cfg.engine.unreal.editor_cmd)
        await _send(
            sock,
            type="log",
            text="Rendering on the GPU (the first render compiles shaders — slow) …",
        )
        await asyncio.to_thread(
            adapter.render_screenshot, project_dir / "preview.png", scene=tspec.map_path
        )
        ok = (project_dir / "preview.png").exists()
        await _send(sock, type="log", text="✓ Rendered." if ok else "No frame captured.")
        await _send(sock, type="done", project=name, preview=f"/preview/{name}", ok=ok)
        return

    if action == "play":
        name = _slug(req.get("name") or "")
        project_dir = workspace / name
        if not (project_dir.is_dir() and next(project_dir.glob("*.uproject"), None)):
            await _send(sock, type="error", text=f"No such project: {name}")
            return
        adapter = UnrealAdapter(project_dir, editor_cmd=cfg.engine.unreal.editor_cmd)
        await _send(
            sock,
            type="log",
            text="Launching the game window — WASD + mouse (first launch is slow) …",
        )
        pid = await asyncio.to_thread(adapter.play, scene=tspec.map_path)
        await _send(sock, type="log", text=f"✓ Game launched (pid {pid}).")
        await _send(sock, type="done", project=name, preview=f"/preview/{name}", ok=True)
        return

    await _send(sock, type="error", text=f"Unknown action: {action}")


def _fmt(assertions: dict) -> str:
    return ", ".join(f"{k}={'✓' if v else '✗'}" for k, v in assertions.items()) or "(none)"
