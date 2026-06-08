# CLAUDE.md — Playsmith

> This file is read automatically by Claude Code at the start of every session.
> It is the single source of truth for what we're building, the decisions already
> made, and how you (Claude Code) should behave in this repo. Read it fully before
> acting. When something here conflicts with a user instruction in chat, follow the
> chat instruction and ask whether to update this file.

---

## 0. The 2026-06-09 re-founding (read this first)

Playsmith started Godot-first / 2D-first / "any local LLM, fully headless." The generated games
were tech demos, not games — the architecture optimized for *"compiles + player_on_floor"*, never
for content, level design, or game feel. We re-founded the project:

- **Unreal Engine 5.x is the engine.** The Godot engine, the GDScript genre skills, and the entire
  old 2D orchestration (studio build-flow, web studio UI, publish pipeline, 2D asset generator)
  have been **removed**. UE 5.7.4 source build lives at `~/UnrealEngine`.
- **Build ON templates, never from an empty scene.** Every game starts from a shipping UE template
  (`TP_ThirdPersonBP` / `TP_FirstPersonBP` / `TP_TopDownBP` — all three are targets) which is
  already a playable, lit, animated game. The LLM is a *director that dresses and tunes it*, not a
  from-scratch level builder. **This is the #1 quality lever.**
- **Tiered LLM.** A frontier model (Claude via the Anthropic API, `ANTHROPIC_API_KEY`) drives the
  director/critic reasoning; local models (Ollama) handle cheap sub-steps. This deliberately relaxes
  the old "any local LLM, fully headless" purity — trying to honor that *and* "polished games" at
  once is exactly why the output was ~2%.
- **A real critic loop, not just structural asserts.** Quality comes from a director→build→critic
  loop where a critic agent scores rendered screenshots + real PIE metrics against a quality rubric
  and sends work back — layered on top of the headless `PLAYSMITH_ASSERT` reality loop.

Build order (stages): **0** re-found docs/config *(done)* → **1** template-foundation (clone a UE
template; prove on third-person first) → **2** editor-in-the-loop + real rendered screenshots/PIE
(drop `-nullrhi`; pin a UE MCP, e.g. `remiphilippe/mcp-unreal`) → **3** director+critic loop → **4**
polish one genre to "actually fun" + package/export. Shared machinery is built once; the three
genres light up on the same rails.

---

## 1. What we're building (one paragraph)

**Playsmith** is an open-source, local-first vibe-coding studio that turns a plain prompt into a
**real, editable Unreal Engine game — and ships it.** Unlike hosted prompt-to-game platforms, the
user owns everything and can self-host the models. Unlike "world model" demos, the output is a real
editable UE project that actually ships. Unlike a raw coding agent, Playsmith has genre-aware
**game-generation skills**, an **autonomous director/critic agent loop**, and a **publishing
pipeline** — so both game developers (to save time) and non-developers (to vibe-code sellable games)
can produce sophisticated games fast.

**Pillars, in priority order:**
1. **Shippable** — produces a real, runnable, *polished* UE game project, and can export/publish it.
2. **Quality first, tiered models** — a frontier model directs/critiques for quality; local models do
   cheap sub-steps. Self-hostable, but quality is the hill we die on.
3. **Any-engine** — Unreal 5.x now, abstracted behind `EngineAdapter` so more can be added.
4. **Open** — Apache-2.0, community-authored skills, no lock-in.

If you ever have to trade off, **"a real, polished, shippable Unreal game"** is the reason to exist —
the emptiest part of the market. See `WHY.md` for the full rationale (note: `WHY.md` still reflects
the pre-pivot framing in places — flag/update it as you touch it).

---

## 2. Decisions already made (do not re-litigate without asking)

| Area | Decision | Why |
|---|---|---|
| Engine | **Unreal Engine 5.x** (5.7.4 at `~/UnrealEngine`) | The user's goal: at least one UE scene done with real polish. Godot output topped out at ~2%. |
| How games are made | **Build ON a shipping UE template**, LLM dresses/tunes it | Quality comes from the foundation, not from LLM-from-scratch. The single biggest lever. |
| Genres | **Third-person, first-person, top-down** (all three) | Each maps to a built-in UE template; shared machinery, per-genre dressing. Prove third-person first. |
| LLM access | **Tiered**: frontier director/critic + local sub-steps | OpenAI-compatible `/v1` for local/most cloud; Anthropic native `/v1/messages` for the frontier director. |
| Verify | **Headless `PLAYSMITH_ASSERT` + a critic loop** | Structural asserts confirm "it runs"; the critic (screenshots + PIE metrics vs. a rubric) drives "it's good." |
| Editor in the loop | **UE editor running (GPU) + a pinned MCP** for real authoring | RTX 3060 is present; you can't judge quality you never render. |
| Language | **Python 3.11+** | MCP/AI tooling is Python-native; type hints, `ruff`, `pytest`. |
| Interface | **CLI/TUI first** (Typer + Rich) | Dev-credible; a GUI is later. |
| License | **Apache-2.0** | Permissive + patent grant. Audit deps. (Note: Unreal has its own EULA + royalties — see the royalty calculator.) |

---

## 3. Architecture (the mental model)

Playsmith is **an agent that directs Unreal Engine and asset generators, guided by skills.**

```
user prompt
   │
   ▼
[ Skills Engine ]  ── picks a genre skill (third-person | first-person | top-down)
   │
   ▼
[ Director ]  ── frontier LLM plans the slice (objective, layout, mechanics, asset choices)
   │
   ▼
[ Agent Loop ]  ── act (tool calls / MCP) → observe (run + render + PIE + read errors) → iterate
   │        ├── [ LLM Gateway ]   tiered: frontier director/critic + local sub-steps
   │        └── [ Engine Adapter ] Unreal — clone-template / author / run / screenshot / verify / export
   │
   ▼
[ Critic ]  ── scores rendered screenshots + PIE metrics vs. a rubric; sends work back until it passes
   │
   ▼
[ Publish Pipeline ]  ── (to be rebuilt for UE) package → store, with compliance helpers
```

Module boundaries under `playsmith/`:
- `playsmith/llm/` — provider abstraction + model router + reliability eval (`gateway`, `anthropic`, `eval`)
- `playsmith/agent/` — the agentic loop, tool definitions, diff approval
- `playsmith/engines/` — `EngineAdapter` interface + `unreal/` (adapter, level_director, templates)
- `playsmith/skills/` — SKILL.md loader (progressive disclosure) + secure marketplace registry
- `playsmith/cli/` — Typer/Rich entrypoints (`version`, `config-check`, `models`, `skills`, `unreal`)

Removed in the re-founding (do not resurrect without asking): `engines/godot/`, the GDScript genre
skills, `studio.py`, `web/`, `publish/`, `assets/`, the Docker stack. The director/critic loop and a
UE-native publish path are forthcoming (stages 3–4).

---

## 4. The non-negotiable feedback loop

The thing that makes this work: **the agent must close the loop on reality.** After changing the UE
project you must:

1. **Run** it (`UnrealEditor-Cmd` headless, or a PIE session with the editor up).
2. **Verify** with the in-engine harness (`verify_game`): it writes machine-readable
   `PLAYSMITH_ASSERT key=value` lines (e.g. `level_loads=true`, `player_exists=true`) the model can
   read — headless, no vision model needed.
3. **Render + critique** (stage 2+): capture a real rendered screenshot and PIE metrics, and have the
   **critic** score them against the genre's quality rubric — content density, playability, framing.
4. **Self-correct** based on what actually happened.

Never declare a game "done" until `verify_game` reports every structural assertion PASS **and** the
critic's quality bar is met — not just "no parse errors." Known structural assertions live in
`engines/base.py::KNOWN_ASSERTIONS`.

---

## 5. How you (Claude Code) should work in this repo

- **Small, verifiable steps.** Build one capability, prove it runs, then move on. Many small commits.
- **Follow the stages** in §0. Default to the next unstarted stage unless the user says otherwise.
- **Unreal correctness.** Build ON the template; do NOT rebuild from an empty scene. Maps/assets are
  binary (`.umap`/`.uasset`) — author via the editor, the UE Python API, or Remote Control / a pinned
  MCP, never by writing those files as text. UE source-build editor boots are slow (~60s warm); never
  `pkill -9` UE repeatedly (it churns the shader DDC). `print()`/`unreal.log()` aren't captured on the
  pythonscript commandlet's stdout — write results to a file via `$PLAYSMITH_UE_OUT` and read it back.
- **Respect the `EngineAdapter` abstraction.** Engine specifics stay behind the adapter.
- **Tiered-model reality.** The director/critic need a frontier model (`ANTHROPIC_API_KEY`); local
  models do cheap sub-steps. When the router crosses local→cloud, it WARNS the user — keep that.
- **Ask before large or destructive changes.** Show diffs. Never delete user game projects.
- **License hygiene.** Check new deps against Apache-2.0. Surface Unreal EULA/royalty implications.
- **Don't over-build.** A runnable, playable slice that ships beats an ambitious one that doesn't.

---

## 6. Coding conventions

- Python 3.11+, type hints everywhere, `ruff` for lint/format, `pytest` for tests (run both; keep green).
- Keep modules small and single-purpose; the boundaries in §3 are real boundaries.
- Config via `config/playsmith.yaml` (see `config/playsmith.example.yaml`). Never hard-code model
  names, endpoints, or paths.
- All LLM calls go through `playsmith/llm/`; all engine actions through an `EngineAdapter`.
- Generated game projects live in the user's workspace dir, **never** inside this repo.
- Dev loop: `source .venv/bin/activate` (deps via `pip install -e ".[dev]"`), then `pytest -q` + `ruff check`.

---

## 7. Definition of Done — the vertical slice

Done when, on this machine (UE 5.7.4 + a frontier model via `ANTHROPIC_API_KEY`, local for sub-steps):

- [ ] A user runs one command with a prompt; Playsmith picks the genre skill and **clones the matching
      UE template** into the workspace (already a playable, lit, animated scene).
- [ ] The **director** dresses it into the requested slice; the agent authors via the editor/MCP.
- [ ] Playsmith **runs + renders** it, reads errors and PIE metrics, and the **critic** iterates until
      the quality rubric passes (not just structural asserts).
- [ ] The user can **open the project in the Unreal editor and edit it.**
- [ ] Playsmith **packages** a playable build; (stretch) a UE-native publish path.

Keep this list honest. Prove it on **third-person first**, then first-person and top-down.

---

## 8. What NOT to do

- Don't rebuild a level from an empty scene with primitives — that's the old ~2% path. Build on a template.
- Don't build toward "world model" / real-time neural video generation (Genie/Oasis). Our output is an
  editable UE project, not ephemeral frames.
- Don't resurrect the removed Godot/2D systems without asking.
- Don't auto-mass-submit near-identical games to stores (Apple 4.2.6 / Google repetitive-content).
- Don't invent a new skill file format — use the SKILL.md standard (`docs/SKILL_SPEC.md`).
- Don't reproduce copyrighted game IP/assets. Generated content is original or template/placeholder.

---

## 9. Pointers

- Public overview & quickstart: `README.md` *(still pre-pivot in places — update as you touch it)*
- Architecture & interfaces: `docs/ARCHITECTURE.md` *(pre-pivot — needs an Unreal-first rewrite)*
- Phased plan & milestones: `docs/ROADMAP.md` *(pre-pivot — needs rewrite)*
- Skill spec & contributing: `docs/SKILL_SPEC.md`, `docs/CONTRIBUTING_SKILLS.md`
- Strategy: `WHY.md` *(pre-pivot framing — flag/update as you touch it)*

> **Docs debt from the re-founding:** the code/config are Unreal-only and green, but several docs
> (`README`, `docs/ARCHITECTURE`, `docs/ROADMAP`, `WHY`, the `BUILD_PLAN*` files, `QUICKSTART`,
> `LAUNCH`) still describe the Godot/2D era. Rewrite them to Unreal-first as part of stage 0/1.
