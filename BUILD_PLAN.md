# Build Plan — start here

> Re-founded **2026-06-09** to **Unreal-first**. The Godot/2D build order is gone. This is the
> concrete, ordered, start-here step list to execute the roadmap — Stage 1 first, then the
> immediate next steps of Stages 2–3. Read `CLAUDE.md` (§0 the re-founding, §4 the feedback
> loop) and `docs/ARCHITECTURE.md` first; `docs/ROADMAP.md` is the matching phased view.

Each step is a small unit of work that **ends in something runnable or verifiable**. Build in
order. Verify the checkpoint, commit, then move on. The non-negotiable rule throughout:
**build ON a shipping UE template; never assemble a level from primitives.** Today's
`unreal new` still builds primitives — replacing that is Step 1.

---

## Prerequisites (do these once)

1. **Unreal Engine 5.7.4** built at `~/UnrealEngine`. Confirm the editor exists:
   `~/UnrealEngine/Engine/Binaries/Linux/UnrealEditor-Cmd -version`.
2. **A frontier model** for the director/critic: set `ANTHROPIC_API_KEY` (Claude, native
   `/v1/messages`). The router falls back to / uses **local** (Ollama, OpenAI-compatible `/v1`)
   for cheap sub-steps and **warns** on every local→cloud crossing.
3. **Python 3.11+** + git. `python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`.
4. Copy `config/playsmith.example.yaml` → `config/playsmith.yaml`; set `engine.unreal.editor_cmd`
   and a `workspace_dir` (generated games live there, **never** in this repo).
5. Sanity-check the skeleton: `pytest -q && ruff check` (green), then `playsmith config-check`
   and `playsmith unreal check` (finds your editor; Remote Control likely "not reachable" until
   Stage 2 — that's expected).

> A baseline already exists: `playsmith unreal new "<name>"` scaffolds + verifies a basic
> playable level **headless** (the `PLAYSMITH_ASSERT` reality loop). It builds primitives, so
> Step 1 swaps that foundation for a real template clone.

---

## Stage 1 — Template foundation (do this first)

### Step 1 — Clone the third-person template instead of building primitives
**Goal:** `playsmith unreal new` clones **`TP_ThirdPersonBP`** into the workspace — already a
playable, lit, animated scene — rather than assembling a floor + pawn from scratch.

- In `playsmith/engines/unreal/`, add a clone path (e.g. `templates.clone_template(...)` +
  an adapter `create_from_template(genre)`), driven via the UE Python API / template API.
- **Handle the gotcha:** the template folder is **not self-contained** — no mannequin /
  prototyping meshes. Either instantiate via UE's **template API**, or also copy
  `~/UnrealEngine/Templates/TemplateResources/High/{Characters,LevelPrototyping}` plus the
  relevant `FeaturePacks/*.upack` so the clone actually has its character + blockout meshes.
- Keep everything behind `EngineAdapter`; don't leak UE paths into the agent loop.

**Checkpoint:** `playsmith unreal new "third person test"` produces a cloned template project in
`workspace_dir`. Open it in the editor (`UnrealEditor <proj>.uproject`) — you walk around an
already-playable, lit scene **with the mannequin present** (not an empty box).

### Step 2 — Verify the cloned template (extend the headless reality loop)
**Goal:** prove the clone is real, headless, before trusting it.

- Extend `verify()` checks for a template clone: `level_loads`, `player_exists`, character mesh
  present, lighting present. Add any new keys to `engines/base.py::KNOWN_ASSERTIONS`.
- Wire it into `unreal new` so a clone that fails verification reports which assert failed.

**Checkpoint:** `playsmith unreal new "third person test"` ends in a `PLAYSMITH_ASSERT` table that
is **all PASS**, headless (`-nullrhi`), with no manual editor step.

### Step 3 — First-person + top-down on the same rails
**Goal:** the other two genres clone + verify with the **same** machinery, no special-casing.

- Genre→template map: third-person → `TP_ThirdPersonBP`, first-person → `TP_FirstPersonBP`,
  top-down → `TP_TopDownBP`. The skill selects the genre; the adapter clones the matching template.
- Each genre needs its own minimal verify expectations (e.g. camera/pawn type).

**Checkpoint:** `unreal new` against a first-person and a top-down prompt each produce a cloned,
verified, openable project. **Stage 1 done** when all three pass on the shared path.

---

## Stage 2 — Editor-in-the-loop + real rendering (next)

### Step 4 — Boot the editor with the GPU and keep it warm
**Goal:** stop being blind — render for real.

- Add an adapter mode that launches the **full editor with the GPU** (drop `-nullrhi`) and keeps
  a warm, reusable session. Do **not** `pkill -9` UE between calls (it churns the shader DDC).
- Surface a clean start/stop so the agent reuses one editor across a build.

**Checkpoint:** Playsmith starts a GPU editor session on the cloned project and you can confirm
it's up (e.g. `playsmith unreal check` shows Remote Control **reachable**).

### Step 5 — Pin a UE MCP as the authoring/inspection surface
**Goal:** a stable tool surface for the director to drive.

- Pin a UE MCP (e.g. `remiphilippe/mcp-unreal`, ~49 tools, port 8090) **behind the adapter** —
  pin the exact version (the MCP ecosystem moves fast; note it in `docs/ARCHITECTURE.md`).
- Expose a thin set of adapter calls (inspect actors, place/move, set properties) over it.

**Checkpoint:** from Playsmith, list and tweak an actor in the live cloned level through the MCP,
and the change is visible in the running editor.

### Step 6 — Real rendered screenshot + a real PIE session
**Goal:** produce the exact inputs the critic will score.

- Capture a **real rendered** screenshot of the loaded level (HighResShot via the editor — not a
  placeholder/headless stub).
- Run a **real PIE** session and collect machine-readable metrics (player spawned, moved,
  framerate, objective reachable) the agent can read back.

**Checkpoint:** one command yields (a) an honest PNG of the scene and (b) a PIE metrics blob.
**Stage 2 done.**

---

## Stage 3 — Director + Critic loop (then)

### Step 7 — Director: plan the slice and dress the template
**Goal:** turn the cloned template into the *requested* game.

- Director = **frontier model** (`ANTHROPIC_API_KEY`) via the tiered gateway. From the prompt it
  plans the slice — objective, layout, mechanics, asset choices — and emits MCP actions that
  **dress/tune** the clone (place geometry/props, set objective, tune the existing pawn).
- Use **local** models for cheap sub-steps; keep the local→cloud warning.

**Checkpoint:** a prompt produces a recognizably *dressed* third-person level (clearly themed,
with an objective) that still verifies headless and renders in Stage 2.

### Step 8 — Critic: score renders + PIE against a rubric, and close the loop
**Goal:** hold the output to a real bar, automatically.

- Critic agent scores the Stage-2 rendered screenshot + PIE metrics against a third-person
  **quality rubric** (content density, playability, framing, objective reachable).
- **Close the loop:** the critic sends structured feedback to the director; iterate until the
  rubric passes — layered on top of the structural `PLAYSMITH_ASSERT` asserts (structural first).

**Checkpoint:** `playsmith unreal new "<prompt>"` runs director→build→render→critic
autonomously and stops only when **both** the structural asserts and the critic's bar pass.
**Stage 3 done** — this is the heart of the product.

---

## Then: Stage 4 (polish one genre to "actually fun" + package/export)

Per `docs/ROADMAP.md` Stage 4: raise the third-person rubric toward "fun," add the UE-native
`RunUAT BuildCookRun` package/export path, and surface compliance helpers (Unreal royalty —
calculator exists; store rules; AI-content disclosure — guided, never auto-spam). The
**Definition of Done** is a **polished third-person vertical slice that opens & edits in the
Unreal editor**, packaged into a playable build (`CLAUDE.md` §7).

---

## Working rhythm

- One step at a time; verify the checkpoint; `git commit`; then next step. Keep `pytest`+`ruff` green.
- UE editor boots are slow (~60s warm) and source-built — be patient; never `pkill -9` in a loop.
- `print()`/`unreal.log()` aren't captured on the pythonscript commandlet's stdout — write
  results to `$PLAYSMITH_UE_OUT` and read the file back (see the adapter's `_run_python`).
- Maps/assets are binary (`.umap`/`.uasset`) — author via the editor / UE Python / MCP, never text writes.
- Keep engine specifics behind `EngineAdapter`; keep all LLM calls in `playsmith/llm/`.
- When a step reveals a better design, update `docs/ARCHITECTURE.md` **and** `CLAUDE.md` together.
