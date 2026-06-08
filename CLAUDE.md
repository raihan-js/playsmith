# CLAUDE.md — Playsmith

> This file is read automatically by Claude Code at the start of every session.
> It is the single source of truth for what we're building, the decisions already
> made, and how you (Claude Code) should behave in this repo. Read it fully before
> acting. When something here conflicts with a user instruction in chat, follow the
> chat instruction and ask whether to update this file.

---

## 1. What we're building (one paragraph)

**Playsmith** is an open-source, local-first, vibe-coding studio that turns a plain
prompt into a **real, editable game in a real engine — and ships it**. Unlike hosted
prompt-to-game platforms, the user owns everything and can run any model locally.
Unlike "world model" demos, the output is a real editable project that actually ships.
Unlike single-engine vendor AI, Playsmith is engine-agnostic (Godot first, Unreal next).
Unlike a raw coding agent, Playsmith has genre-aware **game-generation skills**,
integrated **AI asset generation**, and a **one-click publishing pipeline**.

**Four pillars, in priority order:**
1. **Shippable** — produces a real, runnable, editable game project, and can export/publish it.
2. **Local** — works with any local/self-hosted LLM out of the box (cloud is optional).
3. **Any-engine** — Godot at MVP, Unreal as a power-user track, abstracted so more can be added.
4. **Open** — Apache-2.0, community-authored skills, no lock-in.

If you ever have to trade off, **"shippable real games, locally"** is the hill we die on.
That is the emptiest part of the market and our reason to exist.

> **Read `WHY.md`** for the full strategic rationale: why most AI tools fail, the structural
> moats that keep Playsmith from being another one, the honest risks, and the discipline rules.
> When you're tempted to widen the scope, that file is the answer to why you shouldn't.

---

## 2. Decisions already made (do not re-litigate without asking)

These were chosen deliberately to remove decision paralysis. If the user wants to change
one, update this file and `docs/ARCHITECTURE.md` together.

| Area | Decision | Why |
|---|---|---|
| MVP engine | **Godot 4.x first** | MIT (no royalties), open, text-based scenes, headless export, mature MCP ecosystem. Unreal is Phase 2. |
| MVP scope | **2D first** (platformer), then more genres | Fastest path to a working, shippable demo. 3D is Phase 2. |
| Core language | **Python 3.11+** | The AI-asset tooling (ComfyUI, Hunyuan3D) and the MCP Python SDK are Python-native; keeps the stack coherent. |
| Interface | **CLI/TUI first** (Typer + Rich/Textual), GUI later | Dev-credible, fast to build, mirrors Cline/OpenCode. A Tauri GUI for non-coders is Phase 2+. |
| "Vibe coding" means | **Generate real, editable engine source** the user can open and change | This is our differentiator vs. black-box platforms. Never hide the code. |
| LLM access | **OpenAI-compatible `/v1` API** as the universal interface | One integration covers Ollama, LM Studio, vLLM, LocalAI, llama.cpp, AND cloud by swapping `base_url`. |
| Hosting | **Local-first desktop tool** | Optional hosted tier is a much later, separate concern. |
| License | **Apache-2.0** | Permissive + explicit patent grant; maximizes adoption. Audit every dependency against this. |
| First publish target | **itch.io** via `butler` | Frictionless. Steam (with AI-disclosure helper) and mobile come later. |

---

## 3. Architecture (the mental model)

Playsmith is an **agent that orchestrates engines and asset generators, guided by skills.**

```
user prompt
   │
   ▼
[ Skills Engine ]  ── picks a genre skill (e.g. 2d-platformer) via progressive disclosure
   │
   ▼
[ Agent Loop ]  ── plan → act (tool calls) → observe (run + screenshot + read errors) → iterate
   │        │
   │        ├── [ LLM Gateway ]   any model via OpenAI-compatible /v1 (+ model router)
   │        ├── [ Engine Adapter ] Godot (MVP) | Unreal (Phase 2) — create/edit/run/screenshot/export
   │        └── [ Asset Pipeline ] ComfyUI (2D) | Hunyuan3D/TRELLIS (3D) — optional, falls back to placeholders
   │
   ▼
[ Publish Pipeline ]  ── headless export → itch.io (butler) → later Steam/mobile + compliance helpers
```

Key module boundaries live under `playsmith/`:
- `playsmith/llm/` — provider abstraction + model router
- `playsmith/agent/` — the agentic loop, tool definitions, diff approval
- `playsmith/engines/` — `EngineAdapter` interface + `godot/` (and later `unreal/`)
- `playsmith/assets/` — image/3D generation clients (optional)
- `playsmith/skills/` — SKILL.md loader with progressive disclosure
- `playsmith/publish/` — export + itch.io/butler + compliance helpers
- `playsmith/cli/` — Typer/Rich entrypoints

Full detail: see `docs/ARCHITECTURE.md`. Roadmap: `docs/ROADMAP.md`.

---

## 4. The non-negotiable feedback loop

The thing that makes this work (and what most prompt-to-game tools lack): **the agent
must close the loop on reality.** After generating or editing game code, you must:

1. **Run** the game headlessly (`godot --headless` or a short play session).
2. **Capture** a screenshot and/or the run logs.
3. **Read** the errors/output and the screenshot.
4. **Self-correct** based on what actually happened — not on what the code "should" do.

Never declare a game "done" without having run it and verified it visually and/or via logs.
This loop is implemented in `playsmith/agent/` and used by every skill.

---

## 5. How you (Claude Code) should work in this repo

- **Small, verifiable steps.** Build one capability, prove it runs, then move on. Prefer
  many small commits over one giant one. Each step should end in something runnable.
- **Follow the roadmap.** Default to the next unchecked milestone in `docs/ROADMAP.md`
  unless the user says otherwise. Update the roadmap checkboxes as you complete them.
- **Engine correctness matters.** We target **Godot 4.x** (not 3.x). Use `CharacterBody2D`,
  the `velocity` property, `move_and_slide()` with no arguments, `@export` vars, `.tscn`
  text scenes, and `project.godot`. If unsure about an API, say so rather than guessing.
- **Respect the EngineAdapter abstraction.** Don't hard-code Godot specifics into the agent
  loop or skills engine. Engine-specific logic goes behind the adapter interface so Unreal
  can slot in later.
- **Local-model reality.** Local models need large context (set `num_ctx` to 16K–32K; the
  4K default breaks agentic file editing) and reliable tool-calling. If a local model's
  tool-calling is flaky on a step, the model router may fall back to cloud — but always
  warn the user when it does. Never assume frontier-model reasoning from a 7B local model.
- **Ask before large or destructive changes.** Show diffs. Don't delete user game projects.
- **License hygiene.** Before adding a dependency, check its license is compatible with
  Apache-2.0 and not virally restrictive or commercial-use-limited. Flag anything unusual.
- **Don't over-build.** Placeholders and stubs are fine early. Asset generation is optional
  at MVP — a game with colored-rectangle placeholders that *runs and ships* beats a
  beautiful game that doesn't.

---

## 6. Coding conventions

- Python 3.11+, type hints everywhere, `ruff` for lint/format, `pytest` for tests.
- Keep modules small and single-purpose; the boundaries in §3 are real boundaries.
- Config via `config/playsmith.yaml` (see `config/playsmith.example.yaml`). Never hard-code
  model names, endpoints, or paths.
- All LLM calls go through `playsmith/llm/` — never call a provider SDK directly elsewhere.
- All engine actions go through an `EngineAdapter` — never shell out to `godot` from a skill.
- Generated game projects live in a user-specified workspace dir, **never** inside this repo.

---

## 7. Definition of Done — MVP (Phase 0)

The MVP is done when, on a single consumer machine with a local model via Ollama:

- [ ] A user runs one command, types a prompt like *"a 2D platformer where a cat collects fish and avoids spikes"*.
- [ ] Playsmith picks the `2d-platformer` skill, scaffolds a real Godot 4 project, and writes real GDScript.
- [ ] Playsmith **runs** the game, screenshots it, reads errors, and fixes issues until it runs.
- [ ] The user can **open the project in the Godot editor and edit it.**
- [ ] Playsmith **exports** a playable HTML5/desktop build.
- [ ] (Stretch) Playsmith publishes the build to itch.io via `butler`.

Keep this list honest. When all boxes are checked, we have a real product to launch.

---

## 8. What NOT to do

- Don't build toward "world model" / real-time neural video generation (Genie/Oasis style).
  That's a different paradigm; our output is editable projects, not ephemeral frames.
- Don't add a hosted cloud backend at MVP.
- Don't auto-mass-submit near-identical games to app stores — Apple Guideline 4.2.6 and
  Google's "repetitive content" rules reject this and it would harm users. Publishing means
  shipping *a polished game*, with guided submission, not spamming stores.
- Don't invent a new skill file format. Use the SKILL.md standard (see `docs/ARCHITECTURE.md`
  §Skills) so our skills interoperate with Claude Code / Codex / Cursor.
- Don't reproduce copyrighted game IP or assets. Generated content is original or placeholder.

---

## 9. Pointers

- **Strategy / why this won't be another failed AI tool: `WHY.md`** (read this if scope ever drifts)
- Public overview & quickstart: `README.md`
- Architecture & interfaces: `docs/ARCHITECTURE.md`
- Phased plan & milestones: `docs/ROADMAP.md`
- The first game skill: `game-skills/genres/2d-platformer/SKILL.md`
- Step-by-step build order (start here): `BUILD_PLAN.md`
