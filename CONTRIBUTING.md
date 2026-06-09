# Contributing to Playsmith

Thanks for wanting to help build Playsmith — an open-source, local-first studio that turns a prompt
into a real, editable, shippable **Unreal Engine** game. This guide gets you set up and explains how
we work so your first PR lands smoothly.

By contributing you agree your work is licensed under the project's [Apache-2.0](LICENSE) license,
and you keep your copyright.

---

## Ways to contribute

- **Game-generation skills** — the highest-leverage contribution. A skill is a folder with a
  `SKILL.md` describing how to build a genre on Unreal. See [`docs/SKILL_SPEC.md`](docs/SKILL_SPEC.md)
  and [`docs/CONTRIBUTING_SKILLS.md`](docs/CONTRIBUTING_SKILLS.md). Don't invent a new format — use the
  open SKILL.md standard.
- **Core** — the director/critic loop, the engine adapter, the LLM gateway, the web studio.
- **Docs** — quickstarts, architecture notes, fixing anything stale.
- **Bug reports & ideas** — open an [issue](https://github.com/raihan-js/playsmith/issues) with what
  you ran, what you expected, and what happened (include OS, Python, and UE version where relevant).

## Project ground rules (read these first)

These come straight from [`CLAUDE.md`](CLAUDE.md), the project's source of truth:

- **Build ON a shipping UE template, never from an empty scene.** Quality comes from the foundation;
  the LLM is a *director that dresses and tunes* a real, playable template.
- **Maps/assets are binary** (`.umap`/`.uasset`). Author them via the editor, the UE Python API, or
  Remote Control — **never** by writing those files as text.
- **Respect the module boundaries.** All LLM calls go through `playsmith/llm/`; all engine actions go
  through an `EngineAdapter` (`playsmith/engines/`). Keep engine specifics behind the adapter.
- **Close the reality loop.** After changing a project, run + verify it: the in-engine harness writes
  `PLAYSMITH_ASSERT key=value` lines, and the critic scores the result. Nothing is "done" until the
  structural asserts pass *and* the critic's bar is met — not just "no parse errors."
- **No hard-coded models, endpoints, or paths.** They flow from `config/playsmith.yaml`.
- **Generated game projects live in the user's workspace dir, never inside this repo.**
- **Small, verifiable steps.** Build one capability, prove it runs, then move on — many small commits.

## Development setup

Requires **Python 3.11+**. A local **Unreal Engine 5.x** install (developed against UE 5.7.4) is
needed only for the parts that actually drive the engine; most of the code is unit-tested without it.

```bash
git clone https://github.com/raihan-js/playsmith.git
cd playsmith
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,web]"

cp config/playsmith.example.yaml config/playsmith.yaml   # then edit it
#   - engine.unreal.editor_cmd  → your UnrealEditor-Cmd path
#   - your models/routes        → ANTHROPIC_API_KEY for the frontier tier
# A local .env is auto-loaded (ANTHROPIC_API_KEY / OPENAI_API_KEY / NVIDIA_API_KEY / …).
```

## Run the checks (keep them green)

```bash
pytest -q            # the whole suite — no real Unreal or network needed
ruff check .         # lint
ruff format .        # format
```

Tests mock external systems (the engine, model providers, image APIs) so they're fast and hermetic —
match that style. If you touch the director, critic, refine loop, or web endpoints, add or update a
test. PRs must land with `pytest` and `ruff check` passing.

## Repo layout

```
playsmith/
  llm/        provider abstraction + model router + catalog + image generation
  agent/      the agentic loop, tool definitions, diff approval
  engines/    EngineAdapter interface + unreal/ (adapter, director, critic, refine, templates)
  skills/     SKILL.md loader + secure marketplace registry
  web/        FastAPI studio (server.py + a single self-contained static/index.html)
  cli/        Typer/Rich entrypoints
```

## Sending a pull request

1. Branch off `main`.
2. Make focused commits with clear messages (we use Conventional Commits, e.g. `feat:`, `fix:`,
   `docs:`, `refactor:`).
3. Run `pytest -q` and `ruff check .` — both green.
4. Open the PR describing **what changed and why**, how you verified it, and anything you couldn't
   test (e.g. needs an on-machine UE run). Screenshots help for studio/UI changes.
5. Check new dependencies are Apache-2.0-compatible, and flag anything that isn't.

## A note on the engine's license

Playsmith is Apache-2.0, but **Unreal Engine has its own EULA and royalties** (5% of lifetime gross
above $1M per product; 3.5% via the Epic Games Store). Use `playsmith unreal royalty <gross>` to
estimate. Don't reproduce copyrighted game IP or assets — generated content is original or built on
template/placeholder assets.

Questions? Open an issue or start a discussion. Thanks for building with us. 🛠️
