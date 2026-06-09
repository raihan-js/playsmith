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

> ⚠️ **Status: early but real.** Playsmith now clones a shipping UE template, runs an autonomous
> **director→critic loop** that dresses and *iterates* the level toward a quality bar, verifies it
> in-engine headless, and ships a **web studio** (model switcher, structured prompting, art
> generation, play/preview, file browser). It does **not** yet produce fully polished games — a
> vision-based critic, deeper multi-area content, and one-click packaging are still in progress.
> See [Status / roadmap](#status--roadmap) for exactly what's done and what's next.

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
- 🎬 **Director → critic loop.** A director plans the slice (objective, layout, mechanics, asset
  choices) and authors it; a **critic** then scores the result against a quality rubric (object
  density, variety, spread, verticality, a real goal, lighting) plus the in-engine reality checks,
  and feeds concrete fixes back for another pass until it clears the bar. The headless metrics
  critic runs today (the web studio streams each pass live); scoring real rendered screenshots with
  a vision model is the next step. This is what turns a sparse first pass into a deliberate level.
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
# 1. Get the source and install (editable, with dev + web extras)
git clone https://github.com/raihan-js/playsmith.git
cd playsmith
pip install -e ".[dev,web]"

# 2. Create your config from the example, then edit it
cp config/playsmith.example.yaml config/playsmith.yaml
#   - set engine.unreal.editor_cmd to your UnrealEditor-Cmd path
#   - set your models/routes (ANTHROPIC_API_KEY for the frontier tier; OPENAI_API_KEY
#     enables art generation). A local .env is auto-loaded.

# 3. Sanity-check everything resolves
playsmith version
playsmith config-check
playsmith models                  # round-trip the default model (--eval for reliability)

# 4. Scaffold + verify a real, playable Unreal project, then run the director→critic loop
playsmith unreal new "a third-person temple-ruins game"

# 5. Open it in the Unreal editor and edit it by hand — it's a real .uproject.
```

### …or drive the whole thing from the web studio

```bash
playsmith web                     # → http://localhost:8000
```

A self-contained studio: describe a game (with genre / size / vibe chips), watch the agent clone →
verify → **direct → critique → iterate** live, then **play** it in a native UE window, render a
preview, browse the project files, generate **art** into the project, and switch the **model/provider**
from the top-right Settings — all saved to your local config. Needs the `web` extra (step 1).

The full command surface today:

| Command | What it does |
|---|---|
| `playsmith version` | Print the version. |
| `playsmith config-check` | Show how your configuration resolves (providers, routes, fallback, engine). |
| `playsmith models [--eval]` | Show the route table and round-trip the default model; `--eval` measures tool-call reliability. |
| `playsmith skills [list\|search\|install\|remove]` | Browse and manage game-generation skills (the marketplace). |
| `playsmith web [--port]` | Launch the web studio (prompt → clone → direct/critique → play → art). Needs the `web` extra. |
| `playsmith unreal new "<name>"` | Clone + verify a real, playable UE 5.x project, then run the director→critic loop on it. |
| `playsmith unreal dress "<name>" -p "<prompt>"` | Re-run the director→critic loop on an existing project (iterate without re-cloning). |
| `playsmith unreal play "<name>"` | Launch the dressed game in a native window (WASD + mouse). |
| `playsmith unreal shot "<name>"` | Render a headless GPU screenshot of the level. |
| `playsmith unreal check` | Check the Unreal track: editor binary + Remote Control API availability. |
| `playsmith unreal royalty <gross>` | Estimate Unreal EULA royalties owed on a product's lifetime gross. |

More detail in [`docs/QUICKSTART.md`](docs/QUICKSTART.md).

## Status / roadmap

Playsmith was **re-founded on 2026-06-09** as an Unreal-first tool. (It began as a Godot/2D
project; that entire path has been removed.) The work is organized into four stages, built on
shared machinery so all three genres light up on the same rails:

- **Stage 0 — Re-found** ✓ *(done)* — Unreal-only codebase and config; a working CLI.
- **Stage 1 — Template foundation** ✓ *(done)* — clones a shipping UE template (+ its shared
  content) into the workspace and verifies the build-on-template flow end to end.
- **Stage 2 — Rendering** ✓ *(done)* — headless GPU rendering of the level (offscreen) for
  preview screenshots; a native windowed `play` to actually walk around it.
- **Stage 3 — Director → critic** ◐ *(in progress)* — the autonomous loop **runs today**: a
  rubric-based critic scores each pass + the in-engine reality checks and feeds fixes back until
  it clears the bar, streamed live in the web studio. **Next:** a vision critic that scores real
  rendered screenshots, and deeper multi-area content.
- **Stage 4 — Polish + package** — polish one genre to "actually fun," then package/export and
  a UE-native publish path.

Also shipped: a **web studio** (model switcher, structured prompting, art generation, play/preview,
file browser). Still upcoming: the vision critic, richer multi-scene generation, one-click
packaging, and a plugin surface for more background AI agents / integrations (Claude, OpenAI, and
community automations). Full plan in [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Contributing

Playsmith is built in the open, and the highest-leverage contribution is **new
game-generation skills**. A skill is a folder with a `SKILL.md` describing how to build a genre
on Unreal; Playsmith ships a secure marketplace so skills can be searched, installed, and
removed (`playsmith skills ...`) — community-authored, no lock-in. The format follows the open
SKILL.md standard so skills interoperate with other agent tools.

Everything is Apache-2.0 (see [`LICENSE`](LICENSE)). Code is Python 3.11+ with type hints,
`ruff` for lint/format, and `pytest` for tests — keep both green. Start with
[`CONTRIBUTING.md`](CONTRIBUTING.md) for setup, conventions, and how to add a skill.

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

## Author

Built and maintained by **Raihan** ([@raihan-js](https://github.com/raihan-js)) — AI engineer,
founder/CTO of ClarioScope AI. Playsmith is developed in the open; contributions are welcome via
[`CONTRIBUTING.md`](CONTRIBUTING.md), and every contributor keeps their copyright under Apache-2.0.

## License

Apache-2.0 © 2026 Raihan ([@raihan-js](https://github.com/raihan-js)) and the Playsmith
contributors. See [`LICENSE`](LICENSE).
