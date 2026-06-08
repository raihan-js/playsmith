# Build Plan — Phase 2 (Breadth: 3D, a second engine, a skill marketplace)

Continuation of `docs/BUILD_PLAN_PHASE1.md`. **Do not start Phase 2 until Phase 1's Definition of
Done is met** — one 2D genre is genuinely good, art-bearing, editable, and shipped. That is the
whole point of `WHY.md` rule #3. Phase 2 is where breadth finally opens; it stays disciplined by
opening **one axis at a time** and proving each before the next.

> Same rhythm: paste a step, verify the checkpoint, commit. If a step tempts you past the ❌ list,
> stop and re-read the scope decision.

---

## READ THIS FIRST — the scope decision

Phase 2 earns breadth, but on Playsmith's terms (the intersection moat in `WHY.md`): **open + local +
any-engine + owned artifact**. The sequence is deliberate — prove 3D *in Godot* before touching Unreal;
make the marketplace *safe* before opening it to the community.

**Phase 2 is in scope:**
1. 3D support in the Godot adapter (the engine abstraction's first real stress test).
2. The first Godot **3D genre skills** (3D platformer, then a simple FPS — capped at two).
3. A **3D asset pipeline** (Hunyuan3D / TRELLIS) — optional, with loud cleanup caveats and primitive fallback.
4. A **skill marketplace/registry** — discover + install community skills, with validation and **security**.
5. **Router maturity** — an eval harness + per-task reliability thresholds (the router *core* shipped in Phase 1).
6. An **Unreal adapter** (experimental power-user track) behind the existing `EngineAdapter`.
7. (Optional) a **GUI shell** (Tauri) over the same CLI/agent core — only if it stays local-first.

**Explicitly NOT in Phase 2:**
- ❌ Steam / mobile / console publishing → Phase 3.
- ❌ A hosted SaaS / cloud backend → **permanently out** (`WHY.md`; the economics moat depends on it).
- ❌ World-model / real-time neural video → **permanently out** (different paradigm; not an editable artifact).
- ❌ Auto-mass-submission of games → **permanently out** (platform rules; harms users; CLAUDE.md §8).
- ❌ Unlimited genres — cap 3D genres at **two** (3D platformer + simple FPS) for all of Phase 2.
- ❌ "Realistic/AAA/GTA-like" open worlds — still beyond any model's reliable reach; not a target.

---

## The quality bar for Phase 2

Phase 2 is "good" when:
- a user types a prompt and gets a **basic but runnable 3D Godot game** (player stands on a floor, moves,
  a collectible/goal works) — verified by the same reality loop, adapted to 3D;
- an advanced user can run the **Unreal track** end-to-end on a real machine (create → edit → headless build),
  with the royalty implications surfaced;
- anyone can `playsmith skills install <name>` a third-party skill **safely** (provenance shown, untrusted
  code not silently executed) and generate a game with it.

3D asset quality is explicitly *not* promised to be finished — AI 3D needs cleanup, and we say so loudly.

---

## Prerequisites delta (beyond Phase 1)

- **Godot 4.x with 3D** (the standard build already includes it) + export templates.
- **(Optional) a mesh backend** for 3D assets: Hunyuan3D 2.1 (Apache-2.0) or TRELLIS (MIT). GPU-heavy; optional.
- **(Optional) Blender** (for the mesh-cleanup hook). Optional; degrade without it.
- **(Optional, advanced) Unreal Engine 5.x** + the Remote Control API plugin + a Unreal MCP server
  (e.g. `remiphilippe/mcp-unreal`). Only needed for the Unreal track.

---

## Step 0 — Orient + doc hygiene (no features)
**Paste:**
> Read `CLAUDE.md`, `WHY.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, and this file. In 6 bullets,
> confirm the Phase 2 scope + the ❌ list (especially: 3D-before-Unreal, marketplace-safety-before-openness,
> permanent non-goals). Then doc-hygiene only: ensure `docs/ARCHITECTURE.md` §3 reflects that the model
> router already shipped in Phase 1 (so Phase 2's router work is *maturity*, not *core*), and that the
> EngineAdapter interface note covers 3D. Commit as "docs: Phase 2 scope". No features.

**Checkpoint:** docs agree; the router is documented as a Phase-1 deliverable; no code changed.

---

## Step 1 — 3D in the Godot adapter (stress-test the abstraction)
**Paste:**
> Extend `playsmith/engines/godot/` for 3D **without changing the `EngineAdapter` interface or the 2D
> path**. Add 3D templates to `templates.py` (a 3D `project.godot` with an appropriate renderer, a
> `Node3D` main scene, a `CharacterBody3D` controller template using `move_and_slide()`, `velocity`, and
> 3D gravity), and make `run`/`screenshot` work for 3D scenes (a 3D-aware screenshot harness; note the
> same headless-render caveat). Enforce Godot 4 3D conventions (CharacterBody3D, not KinematicBody;
> `@export`; gravity from project settings). Tests with the godot binary mocked, mirroring
> `tests/test_godot_adapter.py`.

**Checkpoint:** the adapter can scaffold and "run" a trivial 3D project headless (mocked in tests; real on
a machine with Godot); the 2D tests still pass unchanged. The abstraction held.

---

## Step 2 — First Godot 3D genre skill (`3d-platformer`)
**Paste:**
> Add `game-skills/genres/3d-platformer/SKILL.md` for a minimal, runnable Godot 4 **3D** platformer:
> a `CharacterBody3D` player on a floor, basic WASD + jump, a collectible, a goal, placeholder primitive
> meshes (BoxMesh/CapsuleMesh) or imported/generated art. Bundle a deterministic `scripts/player_3d.gd`
> movement template (the reliability lever — the model tunes constants, it does not invent 3D movement).
> Mirror the RUN-AND-VERIFY step. Update the router so a clearly-3D prompt selects it. Tests for routing
> 2d vs 3d vs visual-novel.

**Checkpoint:** `playsmith new "a simple 3D platformer where a robot collects orbs"` produces a runnable
3D scene (player stands on the floor, can move/jump), verified by the reality loop. **Depth first:** do not
add the FPS skill until this one is genuinely good.

---

## Step 3 — 3D asset pipeline (optional, loud caveats)
**Paste:**
> Extend `playsmith/assets/` with a mesh backend per `docs/ARCHITECTURE.md` §4: implement `mesh(prompt_or_image,
> out_path)` against Hunyuan3D 2.1 (default, Apache-2.0) or TRELLIS (MIT), behind `available()`. Add an
> optional Blender headless **cleanup hook** (decimate/UV/scale) and import the result into the project as a
> Godot 4 mesh resource. Degrade gracefully to primitive meshes when no backend is present. Surface a LOUD,
> honest caveat every time AI-3D is used: "expect to clean up topology/UVs/scale before this is game-ready"
> (`WHY.md` risk #1 — do not over-promise). Add `playsmith assets "<prompt>" --kind mesh`. Tests mock the
> backend HTTP and assert graceful degradation.

**Checkpoint:** with a mesh backend running, `playsmith assets "a low-poly tree" --kind mesh` writes a mesh
into the project with the cleanup caveat shown; with it off, the game still ships with primitives.

---

## Step 4 — Skill marketplace/registry v1 (the compounding moat — get safety right) ⭐
This is the durable, long-term moat from `WHY.md` ("community skills"). **Security is the hard part.** **Paste:**
> Implement a skill registry in `playsmith/skills/`: `playsmith skills search <q>`, `playsmith skills install
> <name>`, `playsmith skills remove <name>`, sourced from a **curated remote index** (a signed JSON manifest +
> git/https fetch of the skill folder). Requirements:
> 1. **Validation:** every installed skill must pass the `docs/SKILL_SPEC.md` schema (frontmatter, body,
>    scripts/, references/) before it is usable.
> 2. **Security (non-negotiable):** bundled `scripts/` are **never auto-executed on install**; show
>    provenance (source, author, checksum) and require explicit user consent before a skill's scripts run as
>    part of a build; verify a signature/checksum; default the source to the curated index, with third-party
>    sources opt-in and clearly marked "untrusted." Document the threat model in `docs/ARCHITECTURE.md`.
> 3. Install into a user skills dir (e.g. `~/.playsmith/skills/`), discovered alongside the repo's
>    `game-skills/` (the loader already supports multiple roots).
> Tests: install/validate/remove against a fake local index; rejection of a schema-invalid or unsigned skill;
> assert scripts are not executed without consent.

**Checkpoint:** `playsmith skills install <curated-skill>` validates, shows provenance, and the skill is then
usable by `new`; an invalid/unsigned skill is refused; untrusted code never runs silently. **This is the moat
— do not ship it insecure.**

---

## Step 5 — Router maturity (eval-driven fallback)
**Paste:**
> Build a small **eval harness** in `playsmith/llm/` that measures tool-call reliability per (model, TaskType)
> across a fixture set, and uses it to auto-tune the cloud-fallback threshold (the ~80% heuristic in
> `docs/ARCHITECTURE.md` §1). Surface it via `playsmith models --eval`. Keep the Phase-1 user-facing
> local→cloud warning. Tests mock provider responses and assert the threshold logic + that warnings still fire.

**Checkpoint:** `playsmith models --eval` reports per-task reliability and which steps will fall back to cloud,
and the fallback decision is data-driven, not hand-wired.

---

## Step 6 — Unreal adapter (experimental power-user track)
Only after Godot 3D is good. Godot stays the default. **Paste:**
> Add `playsmith/engines/unreal/` implementing the **same `EngineAdapter`** for Unreal 5.x via the Remote
> Control API (port 30010) + an Unreal MCP server (e.g. `remiphilippe/mcp-unreal`): create/edit a project,
> run, and **headless build**. Surface a **royalty calculator** (5% of lifetime gross above $1M per product;
> 3.5% via Epic Games Store "Launch Everywhere with Epic"; EGS revenue royalty-exempt) so users see the cost
> Godot never has. Mark the track clearly **experimental/advanced**; never make Unreal a dependency of the
> core. Pin the MCP server version (the ecosystem changes monthly — ARCHITECTURE "open risks"). Tests mock the
> Unreal control/MCP layer.

**Checkpoint:** on a machine with Unreal + the plugin, an advanced user runs the Unreal track end-to-end
(create → edit → headless build) and sees the royalty estimate; Godot users are unaffected.

---

## Step 7 — (Optional) GUI shell for non-coders
Only if it preserves local-first and never hides the code. **Paste:**
> Add an optional thin **Tauri** (or Electron) front-end that drives the *same* CLI/agent core — a prompt box,
> the diff-approval view, the reality-loop log/screenshot, and buttons for run/export/publish. It must add no
> server, store nothing remotely, and always expose the real project on disk (`WHY.md` moat #1). It is a view
> over the existing core, not a reimplementation. Keep it in a separate package/dir so the CLI stays primary.

**Checkpoint:** the GUI generates and runs a game using the same core the CLI uses, with diffs and the reality
loop visible — and the underlying project is still a plain, editable Godot folder.

---

## Step 8 — Polish, docs, demo
**Paste:**
> Tighten UX/errors across the 3D, marketplace, and (if built) GUI surfaces. Update `docs/QUICKSTART.md` and
> `docs/ROADMAP.md` (check Phase 2 boxes that are truly done). Record a demo: prompt → 3D game, and installing
> + using a community skill. Suggest the 3 highest-leverage Phase 3 items.

**Checkpoint:** a newcomer can make a basic 3D Godot game and install a community skill from the docs.

---

## Phase 2 Definition of Done
A user generates a basic **3D Godot** game (reality-loop verified); an advanced user runs the **Unreal**
track; anyone installs a **third-party skill** with one command, **safely**. Godot + 2D remain the default,
reliable path. Then breadth has been earned without breaking the discipline that keeps Playsmith alive.
