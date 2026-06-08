# Build Plan — Phase 1 (Claude Code handoff)

This is the continuation of `BUILD_PLAN.md`. Phase 0 (route → scaffold → generate → reality-loop →
run → export, all tested with mocks) is **code-complete**. Phase 1 turns that skeleton into something
a stranger would call *good*: the one genre we have looks like a real game, runs on any model
(local or cloud), iterates by natural language, and ships to itch.io.

> **How to use this file:** open the repo in Claude Code (it auto-reads `CLAUDE.md`). Paste the
> prompts below one at a time, verify the checkpoint, `git commit`, move on. Same rhythm as Phase 0.

---

## READ THIS FIRST — the scope decision (and the guardrail)

The grand vision (Unreal, 3D, realistic/AAA, "GTA-like," a chat GUI) is the **destination**. It is
already written into `docs/ROADMAP.md` (Phases 2–3) and `README.md`. Phase 1 deliberately does **not**
pull any of it forward. This is not timidity — it is `WHY.md` rule #3 ("Nail ONE game type excellently
before going wide. Depth before breadth. Always") and risk #1 (the "70% problem"). A locally-hosted
small model cannot produce an AAA open-world game, and neither can a frontier model; promising it is
the demo-magic trap `WHY.md` exists to prevent. So Phase 1 makes a **2D game genuinely good**.

**Phase 1 is in scope (this file):**
1. Provider hardening + a real model router — use any local model *or* any API key (OpenAI, Anthropic,
   OpenRouter, Gemini), and lean on a stronger model for the hard steps, with a warning when it does.
2. Bring-your-own-art — drop in image files and have the agent use them.
3. 2D asset generation (ComfyUI) with graceful placeholder fallback.
4. `playsmith edit "<change>"` — natural-language iteration (the CLI seed of the future chat UX).
5. Publish v1 — one-click itch.io via `butler`.
6. **One** extra genre skill: a **dialogue/visual-novel** "story" skill (the realistic on-ramp to the
   "story mode" ambition — achievable in 2D, no 3D required). Plus the SKILL.md spec + contributor guide.

**Explicitly NOT in Phase 1 (do not let the model wander here):**
- ❌ Unreal, 3D, or any "realistic/GTA/AAA" target → Phase 2+. Hard capability + scope limit.
- ❌ A desktop/chat GUI → Phase 2+. `playsmith edit` gives ~80% of that value at the CLI now.
- ❌ Steam / mobile publishing → Phase 3.
- ❌ More than the one extra genre above. Breadth is capped at 2 total genres for all of Phase 1.

If a step tempts Claude Code toward any ❌ item, stop and re-read this section.

---

## The honest quality bar ("definition of good" for Phase 1)

A Phase 1 build is "good" when a non-coder, on one machine, can:
- type a prompt and get a 2D platformer **or** a short dialogue/story game that runs with no errors
  (verified by in-engine assertions, not just the absence of a crash — see Step 1.5);
- see **real art** in it — either AI-generated 2D sprites or images they supplied — not just colored boxes;
- say `playsmith edit "make the player jump higher and add a second platform"` and watch it change, re-run, and stay runnable;
- `playsmith export --target web` and `playsmith publish --itch me/my-game` to put it online;
- open the project in the Godot editor and keep editing by hand.

Placeholders remain the always-works floor. Art is an upgrade, never a blocker (CLAUDE.md §5).

---

## Prerequisites delta (beyond Phase 0)

- **(Optional) ComfyUI** for 2D asset generation — `http://localhost:8188`. If absent, everything still
  runs with placeholders. Don't make it required.
- **(Optional) butler** (itch.io CLI) for publishing. Only needed for Step 5.
- **(Optional) a cloud API key** to exercise the router's fallback path: OpenAI, OpenRouter, Gemini, or
  Anthropic. Note the Anthropic caveat in Step 1.

---

## Step 0 — Orient + doc hygiene (no features)
**Paste:**
> Read `CLAUDE.md`, `WHY.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, and `docs/BUILD_PLAN_PHASE1.md`
> in full. In 6 bullets, confirm the Phase 1 scope and the explicit NOT-in-scope list. Then make these
> doc-hygiene fixes only (no features yet): (a) fill in `LICENSE` `[YEAR]`/`[COPYRIGHT HOLDER]` and paste
> the full Apache-2.0 text; (b) in `docs/ROADMAP.md`, reorder Phase 1 so the graphics/quality and
> multi-model items come first and cap "more genres" at one (visual-novel/story), matching this build
> plan; (c) per CLAUDE.md §5, mirror any boundary change into `CLAUDE.md` §3 and `docs/ARCHITECTURE.md`.
> Commit as "docs: Phase 1 scope + license".

**Checkpoint:** the summary matches this file (especially the ❌ list), `LICENSE` is complete, and the
roadmap/architecture/CLAUDE docs agree with each other. No code changed.

---

## Step 1 — Provider hardening + model router ⭐ (your "any model" pillar)
This is the highest-leverage step for "small local models aren't as strong as cloud." **Paste:**
> Implement the model router behind the existing seam in `playsmith/llm/` (`TaskType`, `LLMGateway._resolve`)
> per `docs/ARCHITECTURE.md` §1. Requirements:
> 1. **Config:** activate the `llm.routes` block already stubbed in `config/playsmith.example.yaml` — a
>    map of `TaskType` → provider settings `{provider, base_url, model, api_key, num_ctx, kind}`. Unset
>    tasks fall back to the top-level `llm` provider. Add a `provider_kind` field: `"openai"` (default)
>    or `"anthropic"`.
> 2. **Provider kinds:** keep the current OpenAI `/v1/chat/completions` path as `kind="openai"`. Add a
>    thin `kind="anthropic"` adapter that targets `/v1/messages` (Anthropic's native shape, with the
>    `anthropic-version` header and tool-call translation), because Anthropic's OpenAI-compat endpoint
>    ignores strict function-calling schemas and drops prompt caching — unreliable for our tool loop.
>    A user may still point `kind="openai"` at `https://api.anthropic.com/v1/` for quick tests; document
>    the caveat in a comment.
> 3. **Fallback + warning:** if a routed local call fails or returns no usable tool call on a CODING/REASONING
>    step, optionally retry on a configured cloud route. Whenever the router crosses from local to cloud,
>    emit a clear user-facing warning (CLAUDE.md §5 requires this — never silently send code to the cloud).
> 4. Add `playsmith models` enhancements: list every configured route and which provider/model each
>    resolves to. Keep all provider specifics inside `playsmith/llm/` (CLAUDE.md §6).
> Unit-test with `httpx.MockTransport` like `tests/test_llm_gateway.py`: route resolution, the anthropic
> `/v1/messages` request shape, and that a cloud fallback emits a warning.

**Checkpoint:** `playsmith models` shows the route table; with only Ollama configured everything still
works; pointing a route at a cloud key (or `kind="anthropic"`) round-trips; tests green.

---

## Step 1.5 — Assertion-based reality loop ⭐ (make "good" measurable; the "70% problem")
Today the reality loop reliably catches *parse/runtime errors* from logs, but the load-bearing gameplay
claim — "the player stands on the floor and can jump" — is **visual**, and a local text model can't read
a screenshot (headless renders blank anyway). Close the loop with *machine-readable in-engine assertions*
the model can actually read. Cheapest, highest-leverage move against `WHY.md` risk #1. **Paste:**
> Add an **assertion-based verification** path to the reality loop.
> 1. **Harness:** in `playsmith/engines/godot/`, add an assertion harness (like the existing screenshot
>    harness) — a generated probe Node that loads the game's main scene, runs N physics frames, evaluates a
>    set of checks, prints machine-readable lines `PLAYSMITH_ASSERT <key>=<true|false|number>` to stdout, then
>    quits. It must work **headless** (no display needed) — that's the whole point.
> 2. **Adapter + tool:** add `EngineAdapter.verify(checks) -> VerifyResult` (parse the `PLAYSMITH_ASSERT`
>    lines into pass/fail) and a `verify_game` tool in `playsmith/agent/tools.py` that returns each assertion
>    so the model can fix and re-verify — the reality loop, made readable.
> 3. **Skill-declared checks:** extend the SKILL.md contract so each skill declares its genre's assertions
>    (2d-platformer: `player_on_floor`, `player_not_falling`, `can_jump`, `no_errors`). This feeds the SKILL
>    spec in Step 6.
> 4. **Wire it:** make `studio.new_game`/`edit_game` run `verify` as the final authoritative check, replacing
>    the blank-screenshot dependency (keep the screenshot as optional polish for when a display/vision model
>    exists). Update `docs/ARCHITECTURE.md` §2 and `CLAUDE.md` §4 to describe the assertion loop.
> Tests with the godot binary mocked: harness command shape, `PLAYSMITH_ASSERT` parsing, and that a failing
> assertion drives a fix-and-re-verify iteration (extend the FakeAdapter to emit assertion lines).

**Checkpoint:** on a generated platformer, `verify` returns concrete pass/fail per assertion
(`player_on_floor=true`, `can_jump=true`, `no_errors=true`) **headless**; the agent self-corrects when one
fails; and `new`/`edit` only call a build "done" when assertions pass — not just "no parse errors." "Good" is
now measurable.

---

## Step 2 — Bring-your-own-art (`playsmith assets import`)
Cheap, high-value, no GPU. The adapter already has `add_asset(src, dest)`. **Paste:**
> Add user-supplied art support. (a) CLI: `playsmith assets import <file> [--as <res-path>] [--project <dir>]`
> copies an image into the latest (or given) project via `GodotAdapter.add_asset`, confined to the
> workspace. (b) Agent tool: add an `import_asset`/`list_assets` tool in `playsmith/agent/tools.py` so the
> agent can discover and reference dropped-in art when building a scene, preferring real assets over
> placeholders when present. (c) Update the goal builder in `playsmith/studio.py` to mention any imported
> assets. Keep path-escape protection. Tests with the FakeAdapter.

**Checkpoint:** drop a PNG into a generated game with `playsmith assets import cat.png`, regenerate or
edit, and the player/sprite uses it; with no asset supplied, placeholders still appear; tests green.

---

## Step 3 — 2D asset pipeline (ComfyUI), optional + graceful
**Paste:**
> Implement `playsmith/assets/` per `docs/ARCHITECTURE.md` §4: an `AssetGenerator` protocol with
> `image(prompt, kind, out_path)`, `mesh(...)` (raise NotImplemented for now — 3D is Phase 2), and
> `available()`. Add a `ComfyUIClient` that talks to `assets.comfyui_url`, with a sane default SDXL/
> Pixel-Art workflow for sprites. Wire the existing `_generate_asset` tool in `playsmith/agent/tools.py`
> to call it when `available()` is true, and keep the current placeholder message as the fallback when
> it is not. Add `playsmith assets "<prompt>" --kind sprite`. Never make ComfyUI a hard dependency.
> Tests: mock the ComfyUI HTTP calls; assert graceful degradation when `available()` is false.

**Checkpoint:** with ComfyUI running, `playsmith assets "a pixel-art cat"` writes a sprite into the
project; with it off, the agent transparently falls back to placeholders and still ships a runnable game.

---

## Step 4 — `playsmith edit "<change>"` (natural-language iteration)
The CLI seed of the chat experience you want. Reuses the agent loop. **Paste:**
> Add `playsmith edit "<change>" [--project <dir>] [--yes]` in `playsmith/cli/main.py` plus an `edit_game`
> orchestrator in `playsmith/studio.py` that mirrors `new_game` but: resolves the latest (or given)
> project instead of scaffolding, builds an edit goal ("Here is an existing Godot 4 project; make this
> change, then RUN and fix until clean: <change>"), runs `AgentLoop` with the same tools, and does the
> final authoritative reality check. Reuse diff approval. Tests with FakeGateway/FakeAdapter:
> read_file → apply_patch → run_engine → task_complete on an existing project.

**Checkpoint:** after `playsmith new ...`, run `playsmith edit "make the player jump higher and add a
platform"` and watch it patch, re-run headless, and stay runnable — with diffs shown unless `--yes`.

---

## Step 5 — Publish v1 (itch.io via butler)
**Paste:**
> Implement `playsmith/publish/` per `docs/ARCHITECTURE.md` §6: a `butler` wrapper and
> `playsmith publish --itch <user>/<game> [--channel web] [--project <dir>]` that (a) ensures a Web export
> exists (reuse `GodotAdapter.export`), (b) runs `butler push <build> <user>/<game>:<channel>` via the
> configured `publish.itch.butler_path`, and (c) before pushing, prints the AI-content/compliance caveat
> from ARCHITECTURE §6 (itch is lenient, but surface it). butler is optional — fail with a clear install
> hint if missing. Tests with the butler subprocess mocked (pattern from `tests/test_godot_adapter.py`).

**Checkpoint:** with butler configured, `playsmith publish --itch you/your-game` exports and pushes a
playable HTML5 build; without butler, you get a clean, actionable error. **This meets ROADMAP Phase 1
"Publish v1."**

---

## Step 6 — One story-oriented genre skill + the skill spec
Caps breadth at two genres total. The story skill is the feasible nod to "story mode." **Paste:**
> Add a second skill `game-skills/genres/visual-novel/SKILL.md` (a short, runnable Godot 4 dialogue/
> branching-story game: a `CanvasLayer` UI, a typed dialogue box, choices that branch, a couple of
> backgrounds/portraits using imported or placeholder art). Mirror the structure and the RUN-AND-VERIFY
> step from the 2d-platformer skill, with a bundled `scripts/dialogue.gd` deterministic template. Then
> write `docs/SKILL_SPEC.md` (the SKILL.md format for game-gen skills: frontmatter, body, scripts/,
> references/, progressive disclosure) and `docs/CONTRIBUTING_SKILLS.md` (how to add one). Confirm the
> router distinguishes "a jump-and-run with a fox" (→ 2d-platformer) from "a branching story about a
> detective" (→ visual-novel). Tests in `tests/test_skills.py` for routing between the two.

**Checkpoint:** `playsmith skills` lists both; routing picks correctly; `playsmith new "a short branching
story about a lighthouse keeper"` produces a runnable dialogue game. Breadth stops here for Phase 1.

---

## Step 7 — Polish, QUICKSTART, demo
**Paste:**
> Tighten CLI UX/errors with Rich across the new commands. Update `docs/QUICKSTART.md` to cover
> assets/import, `edit`, publish, and the router (incl. the Anthropic OpenAI-compat caveat). Check the
> Phase 1 boxes in `docs/ROADMAP.md` as they're truly done. Suggest the 3 highest-leverage Phase 2 items
> (likely: native-Anthropic adapter polish, first Godot 3D skill, asset-cleanup tooling).

**Checkpoint:** a newcomer can follow QUICKSTART from zero to a published, art-bearing 2D game using a
local *or* cloud model. Record a 60–90s demo: prompt → art → edit → export → itch. That's the Phase 1
launch artifact.

---

## Working rhythm (unchanged from Phase 0)
- One step, one checkpoint, one commit. Keep generated games in `workspace_dir`, never the repo.
- If Claude Code proposes a new dependency, make it justify the Apache-2.0 license compatibility and the
  module boundary it crosses (CLAUDE.md §5–6) before approving.
- When a step reveals a better design, update `docs/ARCHITECTURE.md` **and** `CLAUDE.md` together.
- Anytime the work drifts toward an ❌ item above, stop and re-read "the scope decision."

## Phase 1 Definition of Done
Every box in ROADMAP Phase 1 is checked **and** the "definition of good" above is met on one machine with
a local model — with the cloud route proven as an optional fallback, not a requirement. Then it's worth a
public launch (see ROADMAP Phase 1 launch trigger and `docs/LAUNCH.md`).
