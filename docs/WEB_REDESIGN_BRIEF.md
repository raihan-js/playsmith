# Web UI redesign — handoff brief for Claude (design)

Paste this whole file into Claude (claude.ai Artifacts, Claude Code, or any design agent) to
redesign the Playsmith web interface. It contains the product context, the exact API/WebSocket
contract the new UI must speak to, the screens to design, and the deliverable format.

---

## The product (one paragraph)

**Playsmith** is an open-source, local-first "vibe-coding studio for games": a person types a plain
prompt ("a 2D platformer where a ninja frog collects coins") and an AI agent generates a **real,
editable Godot game project**, runs it, verifies it actually works, and lets them play it in the
browser — then iterate by natural language. Think *Cursor/v0/Bolt, but for making real games you own*.
The output is never a black box: it's real Godot source the user can open and edit.

## Who uses it

Two audiences, design for both: **non-coders** who want to make a game by chatting, and
**developers/tinkerers** who want to see and edit the generated code. The current UI leans dev;
the redesign should feel approachable and a little playful (it's a game studio) without losing the
"real engineering happening" credibility.

## The core loop (what the UI must support)

1. **Describe** a game in a chat box → watch the agent build it **live** (it streams its steps:
   which skill it picked, each file it writes, each time it runs + verifies the game, pass/fail
   on gameplay checks like "player stands on floor").
2. **See the result**: a card saying it runs + which gameplay assertions passed.
3. **Play** it in the browser (the game exports to HTML5 and runs in an iframe).
4. **Browse** the generated project's files/code.
5. **Iterate**: select a project and type a change ("make the player jump higher, add a second
   platform") → the agent edits + re-verifies.
6. **Discover/install** community "skills" (game genres) and generate **art** (sprites/backgrounds).

## What exists today (replace/improve this)

A single dark `index.html` (vanilla JS, no build step) served by FastAPI:
- **Left ~42%**: a chat stream + a composer (textarea, a New/Edit dropdown, a Send button).
- **Right ~58%**: a tabbed panel — **Projects** (list), **Files** (tree + code viewer), **Play**
  (an "Export & play" button → iframe), **Skills** (list).
- It's functional but plain: flat list rows, no thumbnails, the live agent stream is a wall of
  monospace lines, no visual hierarchy, no empty-state delight, minimal motion.

## Design goals

- **A "chat + canvas" layout** like Claude/Cursor: conversation on one side, a living workspace on
  the other. The build stream should feel like watching an agent *work*, not a log dump — group it
  into readable steps (phase → tool calls → verify result) with icons, subtle motion, and a clear
  final result card with **pass/fail gameplay chips**.
- **A real Projects gallery** with **thumbnails** of each game (screenshots), genre tag, "playable"
  badge, and quick actions (Play, Edit, Files).
- **A first-class Play experience**: the game canvas should feel like the centerpiece — large,
  framed nicely, with a "now playing" state and controls hint (arrows to move, space to jump).
- **A clean code/Files browser** (tree + syntax-highlighted viewer) for the dev audience.
- **An Assets/Art panel**: prompt → generate a sprite/background, preview it, see it applied.
- **Great empty states + onboarding**: the first screen should make a non-coder confident to type
  their first game idea (example prompts as clickable chips).
- **Responsive**: works on a laptop; gracefully stacks on narrow widths.
- **Accessible**: keyboard-navigable, sensible contrast, reduced-motion respect.

## Brand / tone

Playful-but-credible. It's about *making and owning real games, locally, with AI*. Lean into:
ownership ("it's yours"), local-first (no cloud lock-in), and the magic of prompt → playable game.
Dark theme by default is fine (current), but a polished one — consider an accent that feels
"creative tool" (electric indigo/violet) with tasteful color for pass(green)/fail(red)/working(amber).
A subtle logo lockup ("🎮 Playsmith") is fine; you may propose a better mark.

## The exact API the new UI must consume (don't change the backend)

Same-origin. JSON over HTTP + one WebSocket. **The redesign is frontend-only** and must speak this:

**REST**
- `GET /api/config` → `{ "model": "gpt-4o", "provider": "openai", "where": "cloud"|"local", "workspace": "/path" }`
- `GET /api/skills` → `[ { "name": "2d-platformer", "source": "builtin"|"<url>", "trusted": true, "description": "…" } ]`
- `GET /api/projects` → `[ { "name": "a-ninja-frog", "skill": "2d-platformer", "prompt": "…", "has_build": true } ]`
- `GET /api/projects/{name}/files` → `{ "name": "...", "files": [ { "path": "Main.tscn", "size": 1234, "text": "<file contents or empty if binary/large>" } ] }`
- `POST /api/projects/{name}/export` → `{ "ok": true, "play": "/play/{name}/index.html" }` or `{ "ok": false, "logs": "…" }`
- `GET /play/{name}/{path}` → static HTML5 game build (already sends COOP/COEP headers; load it in an iframe)
- (Planned, you may design for it) `GET /api/projects/{name}/thumbnail` → a PNG screenshot of the game.

**WebSocket** `‌/ws` — the live build/edit stream:
- Client sends: `{ "action": "new", "prompt": "a 2D platformer …" }` or `{ "action": "edit", "project": "a-ninja-frog", "prompt": "make the player jump higher" }`
- Server streams JSON events, in order:
  - `{ "type": "start", "action": "new", "prompt": "…" }`
  - `{ "type": "phase", "text": "Routed to skill: 2d-platformer" }` (also: "Scaffolded a working base", "Restored the working base game")
  - `{ "type": "tool", "name": "write_file", "args": { "path": "Main.tscn", "content": "…" } }` (tools: read_file, write_file, apply_patch, list_dir, run_engine, verify_game, screenshot, generate_asset, list_assets, task_complete)
  - `{ "type": "observe", "name": "run_engine", "text": "Run finished: OK …" }` (the tool's result, first line is the useful summary)
  - `{ "type": "done", "done": true, "runs_clean": true, "project": "a-ninja-frog", "skill": "2d-platformer", "assertions": { "player_on_floor": true, "no_errors": true }, "summary": "…", "reason": "task_complete" }`
  - `{ "type": "error", "text": "…" }`

Design the chat to render these meaningfully: `phase` = a status pill; `tool` = a step row with an
icon per tool (write/patch/run/verify…); `observe` = a dim sub-line; `done` = the result card with
green/red **assertion chips** + "Open in panel / Play" actions; `error` = a red callout.

## Deliverable

Produce a **single self-contained `index.html`** (inline CSS + vanilla JS, no build step — it's
served directly by FastAPI from `playsmith/web/static/index.html`) **OR**, if you prefer, a small
**React + Tailwind** single-file component set with a note on how to bundle it. Either way:
- Wire it to the real API/WS contract above (mock the responses in a comment block so it runs
  standalone for preview).
- Include the live-build chat, the projects gallery (with thumbnail placeholders), the play canvas,
  the files viewer, and the assets/skills panels.
- Ship polished empty states, loading states, and at least subtle motion on the build stream.

Keep it one screen, fast, and delightful. Make a non-coder want to type their first game idea.
