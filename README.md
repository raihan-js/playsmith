<div align="center">

# 🛠️ Playsmith

### Prompt → a real game, in a real engine, that you actually ship.

**Open-source. Local-first. Any model. Any engine.**

Playsmith is a vibe-coding studio for games. Describe the game you want, and Playsmith
builds a real, editable project in a real engine (Godot today, Unreal next), generates
art for it, runs it to make sure it works, and helps you publish it — all powered by
**your own local LLM** if you want. Your prompts, your models, your code, your game.

</div>

---

> ⚠️ **Status: early development.** This README describes the project's intent and the
> MVP we're building toward. See [`docs/ROADMAP.md`](docs/ROADMAP.md) for what's actually
> shipped. Star the repo to follow along.

## Why Playsmith exists

The AI game-creation space is split into camps that each solve part of the problem:

- **Hosted "prompt-to-game" platforms** are slick but closed — you don't own the output,
  can't run your own model, and can't export a real engine project.
- **"World model" demos** generate playable video in real time, but produce no editable
  game you can ship.
- **Engine-vendor AI** is locked to one commercial engine and ecosystem.
- **Raw AI coding agents** can do anything but know nothing about *making games* — no
  genre knowledge, no asset generation, no path to the store.

**No tool does all of this at once: open + local + any-engine + a real shippable game +
integrated asset generation + a publishing pipeline.** That intersection is empty.
Playsmith fills it.

> Wondering whether this is just another AI tool that'll fizzle? Read [`WHY.md`](WHY.md) —
> the structural moats, the honest risks, and the discipline that keeps Playsmith alive.

## What makes it different

- 🔓 **Fully open source (Apache-2.0).** No lock-in, no proprietary runtime.
- 🖥️ **Local-first, any model.** Works with Ollama, LM Studio, vLLM, LocalAI, llama.cpp —
  anything that speaks the OpenAI-compatible `/v1` API. Cloud models are optional, not required.
- 🎮 **Engine-agnostic.** Godot 4 today; Unreal as a power-user track; built so more engines
  can be added behind one adapter interface.
- ✏️ **Real, editable code.** Playsmith generates an actual engine project you can open and
  edit by hand. It never hides the game behind a black box.
- 🧠 **Self-correcting.** Playsmith *runs* the game, screenshots it, reads the errors, and
  fixes them — it closes the loop on reality, not just on plausible-looking code.
- 🧩 **Game-generation skills.** A growing, community-authored library of genre skills
  (platformer, top-down RPG, match-3, tower defense, visual novel, FPS…) using the open
  [SKILL.md](https://agentskills.io) standard.
- 🎨 **Integrated asset generation.** Local image generation (ComfyUI/Flux) for 2D sprites
  and local 3D generation (Hunyuan3D/TRELLIS) for models — or bring your own art.
- 🚀 **Actually ships.** One-click export and publishing — itch.io first, then Steam (with
  an AI-disclosure helper) and mobile.

## How it works

```
You: "a cozy 2D platformer where a cat collects fish and avoids spikes"
        │
Playsmith picks the 2d-platformer skill, scaffolds a Godot 4 project,
writes real GDScript, generates sprites, RUNS the game, sees a crash,
fixes it, runs again, screenshots a working level...
        │
You: open it in Godot and tweak it → export to HTML5 → publish to itch.io
```

## Quickstart

> Coming together during Phase 0 — see [`BUILD_PLAN.md`](BUILD_PLAN.md). The intended flow:

```bash
# 1. Install Godot 4.x and a local model runner (e.g. Ollama) with a coding model
ollama pull qwen2.5-coder:7b      # or qwen3-coder for stronger hardware

# 2. Install Playsmith
pip install playsmith             # (once published)

# 3. Configure your model (copy and edit the example)
cp config/playsmith.example.yaml config/playsmith.yaml

# 4. Make a game
playsmith new "a 2D platformer where a cat collects fish and avoids spikes"

# 5. Play it, edit it, ship it
playsmith run
playsmith publish --itch you/your-game
```

## Project layout

```
playsmith/
├── CLAUDE.md                  # how Claude Code works in this repo (read first)
├── WHY.md                     # strategy: moats, risks, and why the scope is narrow
├── BUILD_PLAN.md              # step-by-step build order + prompts to paste into Claude Code
├── README.md                  # you are here
├── docs/
│   ├── ARCHITECTURE.md        # system design & module interfaces
│   └── ROADMAP.md             # phased plan + milestones
├── game-skills/               # the shareable game-generation skills library
│   ├── genres/2d-platformer/  # first skill (SKILL.md + scripts)
│   ├── tasks/                 # asset-gen, level-design, ui... (later)
│   └── publish/               # itch, steam-disclosure, mobile... (later)
├── playsmith/                 # the Python package (the tool itself)
│   ├── llm/  agent/  engines/  assets/  skills/  publish/  cli/
└── config/                    # config + example
```

## Roadmap (short version)

- **Phase 0** — Godot 2D vertical slice: prompt → editable, runnable 2D platformer. ⬅ *we are here*
- **Phase 1** — Asset generation + more genres + one-click itch.io publish.
- **Phase 2** — 3D assets + Unreal track + community skill marketplace.
- **Phase 3** — Mobile/Steam publishing with compliance helpers.

Full detail in [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Contributing

Playsmith is built in the open and we'd love help — especially **new game-generation skills**.
A skill is a folder with a `SKILL.md` describing how to build a genre in an engine. See
[`game-skills/genres/2d-platformer/SKILL.md`](game-skills/genres/2d-platformer/SKILL.md)
for the template. Join the Discord (link coming) and check open issues labeled `good first issue`.

## Responsible use

- Playsmith helps you ship **a polished game**, not spam app stores with near-identical
  builds (which Apple and Google reject anyway).
- AI-generated assets may have limited copyright protection in some jurisdictions —
  Playsmith surfaces this so you can make informed choices.
- We provide helpers to disclose AI use where platforms (e.g. Steam) require it.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
