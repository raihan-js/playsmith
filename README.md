<div align="center">

# 🛠️ Playsmith

### Prompt → a real, editable Unreal Engine game — that you actually ship.

**Open-source. Local-first. Quality-first.**

Playsmith is a vibe-coding studio for games. Describe the game you want, and Playsmith
builds on a shipping **Unreal Engine 5.x** template, directs the engine to dress and tune it
into your game, runs it to make sure it actually works, and helps you ship it — driven by a
tiered mix of a frontier model and your own local LLM. Your prompts, your code, your game.

It's for game developers who want to save time, and for non-developers who want to vibe-code
games worth selling.

</div>

---

> ⚠️ **Status: early development, honest about it.** Today Playsmith is an Unreal-only skeleton
> plus a working `playsmith unreal new` that scaffolds and verifies a basic playable level
> headless. It does **not** yet produce polished games — that's the goal it's being built
> toward. See [Status / roadmap](#status--roadmap) for exactly what's done and what's next.

## Why Playsmith exists

The AI game-creation space is split into camps that each solve part of the problem:

- **Hosted "prompt-to-game" platforms** are slick but closed — you don't own the output,
  can't run your own model, and can't export a real engine project.
- **"World model" demos** generate playable video in real time, but produce no editable
  game you can ship.
- **Engine-vendor AI** is locked to one ecosystem.
- **Raw AI coding agents** can do anything but know nothing about *making games* — no
  genre knowledge, no quality loop, no path to a shippable build.

**No tool does the hard thing: turn a prompt into a real, polished, shippable game project,
locally, that you fully own.** That intersection is the emptiest part of the market, and it's
Playsmith's reason to exist.

> Wondering whether this is just another AI tool that'll fizzle? Read [`WHY.md`](WHY.md) for
> the structural rationale, the honest risks, and the discipline that keeps the scope narrow.

## How it works

Quality comes from the foundation, not from asking an LLM to build a game out of empty space.
Three ideas do the heavy lifting:

- 🏗️ **Build ON a shipping UE template — never from an empty scene.** Every game starts from
  a built-in Unreal template (`TP_ThirdPersonBP`, `TP_FirstPersonBP`, or `TP_TopDownBP` — all
  three are targets) that is *already* a playable, lit, animated game. The LLM acts as a
  **director that dresses and tunes** that template. This is the single biggest quality lever.
- 🎬 **Director + critic loop.** A director plans the slice (objective, layout, mechanics,
  asset choices); the agent authors it; then — alongside headless structural checks — a
  **critic** scores rendered screenshots and real in-editor (PIE) metrics against a quality
  rubric and sends work back until it's actually good. *(Critic loop is upcoming — see roadmap.)*
- 🧠 **Tiered LLMs.** A frontier model (Claude via the Anthropic API) drives the director and
  critic reasoning, where judgment matters; cheap local models (Ollama, or any
  OpenAI-compatible `/v1` endpoint) handle the sub-steps. Self-hostable, but quality is the
  hill we die on.

Underneath, the **reality loop** keeps the agent honest: after every change Playsmith runs the
project and verifies it in-engine, emitting machine-readable `PLAYSMITH_ASSERT` lines
(`level_loads`, `player_start_exists`, `floor_exists`, `player_exists`, `goal_exists`,
`no_errors`) that the model reads — no vision model required. Nothing is "done" until the
checks pass.

```
You: "a third-person game in a ruined temple where you reach a glowing exit"
        │
Playsmith picks the genre skill, clones the matching UE template (already playable),
directs the engine to dress it into your slice, RUNS it headless, reads the asserts,
fixes what failed, and verifies again...
        │
You: open it in the Unreal editor and tweak it → package a build → ship it
```

## Quickstart

**Requirements:** Python 3.11+ and a local **Unreal Engine 5.x** install (developed against
UE 5.7.4). For the director/critic reasoning you'll want a frontier model via
`ANTHROPIC_API_KEY`; local sub-steps can use Ollama or any OpenAI-compatible endpoint.

```bash
# 1. Get the source and install (editable, with dev extras)
git clone https://github.com/<your-org>/playsmith.git
cd playsmith
pip install -e ".[dev]"

# 2. Create your config from the example, then edit it
cp config/playsmith.example.yaml config/playsmith.yaml
#   - set engine.unreal.editor_cmd to your UnrealEditor-Cmd path
#   - set your models/routes (ANTHROPIC_API_KEY for the frontier tier)

# 3. Sanity-check everything resolves
playsmith version
playsmith config-check
playsmith models                  # round-trip the default model (--eval for reliability)

# 4. Scaffold + verify a real, playable Unreal project (headless; first build is slow)
playsmith unreal new "a third-person temple-ruins game"

# 5. Open it in the Unreal editor and edit it by hand — it's a real .uproject.
```

The full command surface today:

| Command | What it does |
|---|---|
| `playsmith version` | Print the version. |
| `playsmith config-check` | Show how your configuration resolves (providers, routes, fallback, engine). |
| `playsmith models [--eval]` | Show the route table and round-trip the default model; `--eval` measures tool-call reliability. |
| `playsmith skills [list\|search\|install\|remove]` | Browse and manage game-generation skills (the marketplace). |
| `playsmith unreal new "<name>"` | Scaffold **and verify** a real, playable UE 5.x project (floor + PlayerStart + pawn). |
| `playsmith unreal check` | Check the Unreal track: editor binary + Remote Control API availability. |
| `playsmith unreal royalty <gross>` | Estimate Unreal EULA royalties owed on a product's lifetime gross. |

More detail in [`docs/QUICKSTART.md`](docs/QUICKSTART.md).

## Status / roadmap

Playsmith was **re-founded on 2026-06-09** as an Unreal-first tool. (It began as a Godot/2D
project; that entire path has been removed.) The work is organized into four stages, built on
shared machinery so all three genres light up on the same rails:

- **Stage 0 — Re-found** ✓ *(done)* — Unreal-only codebase and config; a working
  `playsmith unreal new` that scaffolds and verifies a basic playable level headless.
- **Stage 1 — Template foundation** — clone a shipping UE template into the workspace and prove
  the build-on-template flow end to end (third-person first).
- **Stage 2 — Editor-in-the-loop rendering** — drive a live UE editor (GPU) for real rendered
  screenshots and PIE metrics, via a pinned Unreal MCP.
- **Stage 3 — Director + critic** — the autonomous director→build→critic quality loop that
  scores screenshots + PIE metrics against a rubric and iterates.
- **Stage 4 — Polish + package** — polish one genre to "actually fun," then package/export and
  a UE-native publish path.

Today the build-on-template foundation, the director/critic loop, editor-in-the-loop
rendering/PIE, and a UE publish path are **upcoming**, not done. Full plan in
[`docs/ROADMAP.md`](docs/ROADMAP.md).

## Contributing

Playsmith is built in the open, and the highest-leverage contribution is **new
game-generation skills**. A skill is a folder with a `SKILL.md` describing how to build a genre
on Unreal; Playsmith ships a secure marketplace so skills can be searched, installed, and
removed (`playsmith skills ...`) — community-authored, no lock-in. The format follows the open
SKILL.md standard so skills interoperate with other agent tools.

Everything is Apache-2.0 (see [`LICENSE`](LICENSE)). Code is Python 3.11+ with type hints,
`ruff` for lint/format, and `pytest` for tests — keep both green.

> **A note on the engine's license:** Playsmith is Apache-2.0, but Unreal Engine has its own
> EULA and **royalties** (5% of lifetime gross above $1M per product; 3.5% via the Epic Games
> Store). Use `playsmith unreal royalty <gross>` to estimate what a product would owe.

## Responsible use

- Playsmith helps you ship **a polished game**, not spam app stores with near-identical builds
  (which Apple and Google reject anyway).
- Generated content is original or built on template/placeholder assets — not copyrighted game
  IP.
- We surface compliance and AI-disclosure considerations where platforms require them.

## Learn more

- [`CLAUDE.md`](CLAUDE.md) — the canonical source of truth: what we're building and the decisions made.
- [`WHY.md`](WHY.md) — the strategy, moats, and honest risks.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — system design and module interfaces.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — the phased plan and milestones.
- [`docs/QUICKSTART.md`](docs/QUICKSTART.md) — step-by-step setup.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
