# Roadmap

> Re-founded **2026-06-09** as an **Unreal-first** tool. The Godot/2D era (Godot engine,
> GDScript genre skills, the web studio UI, `publish/`, `assets/`, `studio.py`, Docker) was
> **removed** — clean slate. See `CLAUDE.md` §0 for the full re-founding rationale and
> `docs/ARCHITECTURE.md` for the current system. This roadmap is the phased plan; update the
> checkboxes as milestones land.

The discipline: **build ON a shipping Unreal template** (already a playable, lit, animated
scene) and let a frontier LLM *direct* it — never build a level from an empty scene with
primitives. That from-scratch path is exactly why the old output topped out at ~2%. Quality
comes from the foundation, not from the model inventing geometry. Prove everything on
**third-person first**, then light up first-person and top-down on the same rails.

The spine is four stages. Each ends in something runnable/verifiable. Don't jump ahead —
the editor-in-the-loop rendering (Stage 2) and the critic (Stage 3) are the heart of the
product, and Stage 1 exists to give them a real scene to work on.

---

## What exists today (honest snapshot)

The repo is an **Unreal-only skeleton**, code-complete and green (`pytest -q` + `ruff check`),
but everything in Stages 1–4 below is **not done yet**. Concretely, today you have:

- `playsmith unreal new "<name>"` — scaffolds **and verifies** a basic playable level
  (floor + lights + PlayerStart + pawn + goal) by driving `UnrealEditor-Cmd` **headless** via
  the UE Python API, then reads back `PLAYSMITH_ASSERT` lines (`level_loads`, `player_exists`, …).
  This is the headless reality loop working — but it **builds primitives**, not a template.
- `playsmith unreal check` / `unreal royalty` — editor + Remote Control probe; EULA royalty calc.
- A **tiered LLM gateway + model router** (`playsmith/llm/`): OpenAI-compatible `/v1` for
  local/most cloud, native Anthropic `/v1/messages` for the frontier director; `models --eval`
  reliability harness; warns on every local→cloud crossing.
- The **agent loop** (`playsmith/agent/`), **skills loader + secure marketplace**
  (`playsmith/skills/`: `skills list/search/install/remove`, untrusted-by-default).
- CLI: `version`, `config-check`, `models`, `skills`, `unreal`.

What's missing (the whole point of the stages below): cloning a real UE template instead of
primitives; running the editor with the GPU for **real rendered** screenshots and PIE; and the
**director→critic** loop that scores those renders against a quality rubric.

---

## Stage 0 — Re-found the docs & config  ✅ DONE

**Goal:** burn the Godot/2D boats; make the code, config, and tests Unreal-only and green.

- [x] Godot engine, GDScript genre skills, `studio.py`, `web/`, `publish/`, `assets/`, Docker — **removed**.
- [x] `playsmith/engines/unreal/` is the only adapter; `EngineAdapter` abstraction kept.
- [x] Tiered LLM gateway + router + `models --eval`; skills loader + secure marketplace retained.
- [x] `config/playsmith.example.yaml` is Unreal-first (`engine.unreal.editor_cmd`).
- [x] Tests + lint green; `CLAUDE.md` rewritten to the re-founding.
- [x] `docs/ROADMAP.md` + `BUILD_PLAN.md` rewritten Unreal-first (this pass).

**Done means:** the tree only describes/exercises Unreal, and a fresh `pytest`/`ruff` run is clean.

---

## Stage 1 — Template foundation  ⬅ START HERE

**Goal:** `playsmith unreal new` **clones a shipping UE template** into the workspace —
already a playable, lit, animated scene — instead of assembling primitives. Prove it on
**third-person first**, then bring first-person + top-down up on the same rails.

- [ ] `unreal new` clones **`TP_ThirdPersonBP`** into the workspace and the result opens,
      runs, and verifies (`level_loads`, `player_exists`, mannequin present, lighting present).
- [ ] **Known gotcha handled:** the UE template folder is **not self-contained** — it ships no
      mannequin / prototyping meshes. The clone must either instantiate via UE's **template API**,
      or also copy `~/UnrealEngine/Templates/TemplateResources/High/{Characters,LevelPrototyping}`
      plus the relevant `FeaturePacks/*.upack`, so the cloned project actually has its character and
      blockout meshes.
- [ ] Genre→template map: third-person → `TP_ThirdPersonBP`, first-person → `TP_FirstPersonBP`,
      top-down → `TP_TopDownBP`. The skill picks the template; the adapter clones it.
- [ ] First-person + top-down clone + verify on the **same** rails (shared machinery, per-genre target).

**Done means:** `playsmith unreal new "<prompt>"` produces a real cloned template project in the
workspace that **runs headless and verifies**, and a human can open it in the editor and walk
around an already-playable scene — for all three genres, third-person proven first.

---

## Stage 2 — Editor-in-the-loop + real rendering

**Goal:** stop being blind. Run the UE editor **with the GPU** (drop `-nullrhi`), capture
**real rendered** screenshots, and run a **real PIE** (Play-In-Editor) session — so quality can
be judged on what's actually on screen, not just structural asserts.

- [ ] Boot the editor with the GPU (RTX 3060 present); a warm, reusable editor session
      (don't `pkill -9` UE repeatedly — it churns the shader DDC).
- [ ] **Pin a UE MCP** (e.g. `remiphilippe/mcp-unreal`, ~49 tools, port 8090) behind the adapter
      as the authoring/inspection surface.
- [ ] Capture a **real rendered screenshot** of the loaded level (not a placeholder).
- [ ] Run a **real PIE session** and collect metrics (e.g. player spawned, moved, framerate,
      objective reachable) the agent can read back.

**Done means:** for a cloned template, Playsmith produces an honest rendered screenshot **and**
PIE metrics on demand — the inputs the critic needs in Stage 3.

---

## Stage 3 — Director + Critic loop

**Goal:** turn the template into the *requested* game, and hold it to a real bar.

- [ ] **Director** (frontier model): from the prompt, plan the slice — objective, layout,
      mechanics, asset choices — and drive the MCP to **dress/tune** the cloned template.
- [ ] **Critic** (agent): score the Stage-2 rendered screenshots + PIE metrics against a genre
      **quality rubric** (content density, playability, framing, objective reachable).
- [ ] **The loop closes:** the critic sends work back to the director until the rubric is met —
      layered on top of the headless `PLAYSMITH_ASSERT` reality loop (structural first, quality next).

**Done means:** prompt → dressed third-person slice that passes both the structural asserts **and**
the critic's quality bar, with the loop iterating autonomously until it does.

---

## Stage 4 — Polish to "actually fun" + package/export

**Goal:** take **one** genre (third-person) from "passes the rubric" to "a person wants to keep
playing," and ship it.

- [ ] Polish pass: real game feel, pacing, a complete objective loop — the rubric raised toward "fun."
- [ ] **UE-native package/export** path (`RunUAT BuildCookRun`) to a playable build.
- [ ] Compliance helpers surfaced: Unreal EULA/royalty (calculator exists), store rules
      (Apple 4.2.6 / Google repetitive-content), AI-content disclosure — guided, never auto-spam.

**Done means:** a third-person vertical slice that is genuinely fun, packaged into a playable
build, with the right disclosures generated for a human-guided submission.

---

## Definition of Done (the whole roadmap)

**A polished third-person vertical slice that opens & edits in the Unreal editor** — generated
from a prompt by cloning a UE template and directing/critiquing it to a real quality bar, then
packaged into a playable build. Prove it on third-person first; first-person and top-down ride
the same rails. (See `CLAUDE.md` §7 for the exact checklist.)

---

## Always-on (every stage)

- Keep `pytest` + `ruff` green; small, verifiable commits.
- Respect the `EngineAdapter` boundary — engine specifics stay behind it.
- License hygiene against Apache-2.0 on every dependency; surface Unreal EULA/royalty.
- Update these checkboxes + `BUILD_PLAN.md` as milestones land; keep docs the source of truth.

## Explicitly out of scope (for now)

- Resurrecting the removed Godot/2D systems (don't, without asking — `CLAUDE.md` §8).
- Real-time "world model" / neural video generation (Genie/Oasis). Our output is an editable UE project.
- A hosted cloud backend / SaaS tier (a much later, separate track).
- Auto mass-submission of near-identical games to stores (Apple 4.2.6 / Google repetitive-content).
