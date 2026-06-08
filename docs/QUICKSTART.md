# Quickstart

Get from zero to a real, runnable Unreal Engine 5.x project — scaffolded and verified by
Playsmith, then yours to open and edit in the Unreal editor. For the bigger picture see
`README.md`; for the full command list, `playsmith --help`.

> **Where Playsmith is today (be honest):** `playsmith unreal new` builds and verifies a
> **basic playable level** (floor + PlayerStart + pawn + goal), headless, via the UE Python API.
> That's the foundation — not a polished game yet. Building *on* a shipping UE template, the
> director/critic loop, and rendered-screenshot review are upcoming stages. See `docs/ROADMAP.md`.

---

## 1. Prerequisites

Required:

1. **Python 3.11+** (`python3 --version`).
2. **Unreal Engine 5.x** installed locally (developed against UE 5.7.4). Playsmith drives the
   headless editor, `UnrealEditor-Cmd`. You'll point `engine.unreal.editor_cmd` at that binary in
   your config (it's auto-discovered from `~/UnrealEngine` if you leave it blank).

A model — pick at least one:

- **A frontier model** (recommended for the director/critic work) via the Anthropic API. Export
  your key: `export ANTHROPIC_API_KEY=sk-ant-...`.
- **A local model** via [Ollama](https://ollama.com) for cheap sub-steps:
  ```bash
  ollama pull qwen2.5-coder:7b
  ```
  Ollama serves an OpenAI-compatible endpoint at `http://localhost:11434/v1`. Any
  OpenAI-compatible server works (LM Studio, vLLM, llama.cpp).

> Playsmith is **tiered**: a frontier model drives reasoning while a local model handles the cheap
> steps. You can run all-local or all-frontier, but the tiered setup is what we tune for.

> ⚠️ **Context window matters** for local models. Keep `num_ctx` at 16K–32K (default 16384).
> The 4K default breaks agentic editing.

---

## 2. Install

```bash
git clone https://github.com/raihan-js/playsmith && cd playsmith
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"      # drop [dev] if you don't want ruff/pytest
```

---

## 3. Configure

```bash
cp config/playsmith.example.yaml config/playsmith.yaml
```

Edit `config/playsmith.yaml`. The keys that matter:

- `workspace_dir` — where generated projects are written (default `~/playsmith-games`; never inside
  this repo).
- `llm.*` — your default model (`provider`, `base_url`, `model`, `api_key`, `num_ctx`, `kind`).
  Use `kind: "openai"` for Ollama/LM Studio/vLLM/OpenAI; `kind: "anthropic"` for Claude.
- `engine.default` — `unreal`.
- `engine.unreal.editor_cmd` — full path to your `UnrealEditor-Cmd` (blank = auto-discover from
  `~/UnrealEngine`).
- `skills.registry_url` / `skills.dir` — the community-skill marketplace and where installs land.

**Tiered LLM example** — keep a local default for cheap steps, route the heavy reasoning/coding to
Claude. Add this under `llm:` in `config/playsmith.yaml`:

```yaml
llm:
  provider: "ollama"
  base_url: "http://localhost:11434/v1"
  model: "qwen2.5-coder:7b"
  api_key: ""
  num_ctx: 16384
  kind: "openai"

  routes:
    reasoning:                       # director / critic / planning
      provider: "anthropic"
      base_url: "https://api.anthropic.com/v1"
      model: "claude-opus-4-8"
      api_key: "${ANTHROPIC_API_KEY}"
      kind: "anthropic"
    coding:
      provider: "anthropic"
      base_url: "https://api.anthropic.com/v1"
      model: "claude-sonnet-4-6"
      api_key: "${ANTHROPIC_API_KEY}"
      kind: "anthropic"

  fallback:                          # used when the local model fails / returns no tool call
    provider: "anthropic"
    base_url: "https://api.anthropic.com/v1"
    model: "claude-sonnet-4-6"
    api_key: "${ANTHROPIC_API_KEY}"
    kind: "anthropic"
```

`${ANTHROPIC_API_KEY}` is read from your environment. Whenever the router crosses from a local
model to a cloud one, it warns you (your code is leaving the machine).

---

## 4. Verify your setup

Each command proves one piece before you generate a project:

```bash
playsmith config-check        # shows how your config resolves (workspace, llm, routes, fallback, engine)
playsmith models              # shows the route table + round-trips a message to your default model
playsmith unreal check        # checks the UnrealEditor-Cmd binary + Remote Control API availability
```

If `models` fails, your model server (or API key) isn't reachable. If `unreal check` can't find the
editor, set `engine.unreal.editor_cmd` to your full `UnrealEditor-Cmd` path.

You can also list what you can build:

```bash
playsmith skills              # lists installed game-generation skills
```

---

## 5. Make your first project

```bash
playsmith unreal new "my first unreal level"
```

What happens: Playsmith creates a real UE project under your `workspace_dir`, asks the LLM to theme
a level from your prompt (falling back to a safe default if no model is available), then **scaffolds
a lit, playable level** and **verifies it in-engine** — the headless `PLAYSMITH_ASSERT` reality
loop. It checks `level_loads`, `player_start_exists`, `floor_exists`, `player_exists`, and
`goal_exists`, and reports each as PASS/FAIL.

> ⏳ **The first editor boot is slow** (a UE source build can take a minute or more to warm up).
> That's expected — let it run.

Pass `--config PATH` to use a config file other than `config/playsmith.yaml`.

---

## 6. Open it in the Unreal editor

When `unreal new` succeeds it prints the project path and the open command. The project lives at
`<workspace_dir>/<slug>/<Name>.uproject`. Open it with:

```bash
UnrealEditor ~/playsmith-games/my-first-unreal-level/*.uproject
```

The project is **yours** — a real, editable Unreal project. Open the level, walk around, change
anything.

---

## 7. Handy extras

```bash
# Community skills (marketplace) — installs are integrity-checked and never auto-run:
playsmith skills search rpg
playsmith skills install <name>                # untrusted skills need --allow-untrusted
playsmith skills remove <name>

# Measure tool-call reliability per provider/route (router maturity):
playsmith models --eval

# Estimate Unreal EULA royalties (5% above $1M lifetime gross per product; 3.5% via EGS):
playsmith unreal royalty 2000000
playsmith unreal royalty 2000000 --egs --egs-exempt 500000

# Version:
playsmith version
```

> Community skills are *code you're trusting* — their scripts and instructions drive the agent.
> Playsmith verifies a checksum, refuses untrusted skills unless you pass `--allow-untrusted`, and
> never executes anything on install.

---

## Where to go next

- **`docs/ROADMAP.md`** — the staged plan: build-on-template foundation, the director/critic loop,
  rendered-screenshot review, packaging/export.
- **`docs/ARCHITECTURE.md`** — the mental model: skills → director → agent loop → critic, and the
  `EngineAdapter` abstraction.

---

## Troubleshooting

- **`unreal check` / `unreal new` can't find the editor.** Set `engine.unreal.editor_cmd` to the
  full path of your `UnrealEditor-Cmd`, or place your engine at `~/UnrealEngine` for auto-discovery.
- **First build hangs for a long time.** The first UE editor boot is genuinely slow; give it time.
- **`models` fails.** Your model server isn't running (start Ollama) or your `ANTHROPIC_API_KEY`
  isn't exported / the route's `api_key` is wrong. `playsmith config-check` shows what resolved.
- **Local model is flaky.** Raise `num_ctx` (16K → 32K), or configure `llm.routes` / `llm.fallback`
  to a frontier model for the hard steps.
