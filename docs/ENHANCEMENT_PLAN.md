# Playsmith — The Ultraplan (next-gen enhancements, micro-goal by micro-goal)

> Written after stress-testing the system with a full AAA fighting-game prompt (*Ashenveil
> Chronicles*). It opens with the **root-cause findings** — why output is "the same template every
> time" — then a **step-by-step, micro-goal** enhancement plan. The rule from here: *small verifiable
> steps, one at a time, verified in-engine before moving on.* Time is not the constraint; quality is.

---

## Part 1 — The stress-test verdict (what's actually broken)

We fed it a 5,000-word dark-fantasy fighting game (6 characters, GAS, 5-act branching story, Chaos
destruction, MetaHumans). It produced **a generic third-person arena with a grey mannequin** — the
same as every other prompt. Here is *why*, in priority order:

### 🔴 ROOT CAUSE #1 — Headless deletions don't persist (the "every game is the same" bug)
The third-person template's `Lvl_ThirdPerson` is a **World Partition / One-File-Per-Actor** level.
In the headless `pythonscript` commandlet, `EditorActorSubsystem.destroy_actor()` + `save_dirty_packages()`
removes actors *in the session* but **does not delete their external-actor packages on disk** — so on
the next load they stream right back. Proven by diagnostic: re-dressing went **20 → 40 placed objects**
(stacking, with duplicate `PS_cube_0`), and the **55 template demo objects never cleared**.

Consequences that explain everything the user saw:
- The template ships **~55 prototype demo blocks** that **dominate every level** → every prompt looks
  like "the UE template demo."
- Our dressing **accumulates as clutter** on each pass instead of replacing.
- `objects_placed=PASS` is a false comfort — *placing* works, *deleting/replacing* does not.

**The fix is the editor-in-the-loop** (a live editor persists OFPA deletions correctly — already
built, just not turned on), **or** a headless external-actor-package deletion path. *Nothing else in
this plan matters until this is fixed* — it's why iteration appears to do nothing.

### 🔴 ROOT CAUSE #2 — The renders never reflected reality
Because of #1, every establishing render across the whole session was byte-near-identical — I was
"verifying" against a stale level. **No quality work can be trusted without a render that loads the
actual saved level.** (Editor-in-the-loop + SceneCapture fixes this too.)

### 🟠 GAP #1 — The director only does *level dressing*
It reduces *any* prompt — including a 6-character fighting game — to "place ~20 objects by role." It
has **no concept** of characters, movesets, mechanics, combat, story, UI, or audio. A fighting game
needs all of those; Playsmith builds the *stage* and nothing else.

### 🟡 SMALLER BUGS (already fixed this session)
- Title ate the `GAME TITLE:` label → now parses it (`Ashenveil Chronicles: Shattered Bloodlines`).
- Theme matched substrings (`choi**ces**` → `ice` → "frozen") → now word-boundary; added an
  "ashen void" dark-fantasy theme.
- Clone config was read-only → build crashed → fixed.

---

## Part 2 — The discipline (how we work from here)

1. **One micro-goal at a time.** Each step below is small and independently verifiable.
2. **Verify in-engine, not in theory.** Every UE-touching step ends with: build/dress → render the
   *real* saved level → look at it → confirm the change. No "it should work."
3. **Editor-in-the-loop is the default.** Bring the editor up with Remote Control; it's the only way
   deletions/persistence/rendering are trustworthy. Headless stays as a degraded fallback.
4. **No new feature until the foundation under it is verified.** (We learned this the hard way.)

---

## Part 3 — Phase 0: make iteration REAL (the unblock — do this first)

Until these pass, everything downstream is built on sand.

> **Status — proven in-engine (headless), 2026-06-10.** The keystone fix landed: `_ps_delete` deletes
> each destroyed actor's external-actor `.uasset` file, so World Partition deletions persist. Measured
> on a real third-person project across three *fresh loads* (the only test that catches the OFPA bug):
>
> | stage | PS_ objects | demo blocks | floor |
> |---|---|---|---|
> | baseline (broken) | 40 | 45 | 10 |
> | after dress 1 (fix) | 3 | **0** | 10 |
> | after dress 2 (re-dress) | **3** | 0 | 10 |
>
> Demo course cleared (45→0) and *stayed* cleared; PS_ dressing replaced not stacked (40→3→3); floor
> preserved. **0.1, 0.2, 0.4 ✅.** 0.3 (a render that loads the saved level) still wants the live
> editor — `playsmith unreal serve` now turns it on in one command (Route A).

- **0.1 — Persist deletions.** ✅ Route B (headless): `_ps_delete` removes each actor's external
  package file after `destroy_actor`. Route A (editor-in-the-loop) persists OFPA deletions natively.
  **Done — re-dressing held at 3 PS_ (no 20→40 stacking) and the demo blocks are gone (45→0).**
- **0.2 — Clear the template demo course, verified.** ✅ `verify_clean` fresh-loads and emits
  `template_demo_clear` + `objects_present`. **Done — fresh-load shows 0 demo objects, floor + PS_
  dressing intact.**
- **0.3 — Trustworthy render.** Establishing render (SceneCapture via the live editor) that loads the
  *saved* level. **Done = two different prompts produce two visibly different renders.** *(Pending: run
  via `unreal serve` now that the level genuinely changes.)*
- **0.4 — Idempotent dressing.** ✅ A re-dress *replaces*, never stacks. **Done — PS_ count 3→3 across
  re-dress; no duplicates.**

**Exit criteria for Phase 0:** two prompts → two clearly different, clutter-free levels, confirmed by
render. *This is the whole ballgame for "why is it bad."* — **foundation proven; render-diff is the
last check, via the live editor.**

---

## Part 4 — Phase 1: make the *stage* good (real assets + look)

- **1.1** Real-asset dressing verified end-to-end (Megascans/Fab via discovery or a manifest pack) —
  a level made of real rock/ruins/foliage, not cubes. (Code shipped; verify live.)
- **1.2** Lumen/Nanite/VSM confirmed improving the look on a real scene (config shipped; verify).
- **1.3** Theme → asset-set mapping (frozen→ice kit, ashen→ruins kit, …) so the *kit* changes with the
  theme, not just colours.
- **1.4** Ground/sky/post per theme (snow ground + cool fog for frozen; ash haze for ashen).
- **1.5** Composition pass: the critic scores a *real* render (vision) for density/framing, not just
  object counts — so "looks good" is measured, not assumed.

**Exit:** a frozen prompt and an ashen prompt produce two genuinely different, real-looking arenas.

---

## Part 5 — Phase 2: characters (from "a grey robot" to a cast)

The Ashenveil prompt names **six** characters; Playsmith places **one** mannequin. Micro-goals:

- **2.1** Parse a character roster from the prompt (names, archetypes, stats) into a structured spec.
- **2.2** Swap the player pawn to a chosen character look (mesh + tint) — verified in-game (needs the
  editor-in-the-loop, per the BP-component lesson).
- **2.3** **MetaHuman** integration: a real face/body per character (free, photoreal). One character first.
- **2.4** A character-select screen (UMG) listing the parsed roster.
- **2.5** Per-character spawn + camera framing for a 1v1 arena.

**Exit:** pick a character from the prompt's roster and spawn it (not the default mannequin).

---

## Part 6 — Phase 3: it becomes a *game*, not a walk (mechanics via GAS)

This is the largest gap — Playsmith has **zero** gameplay systems. Build the smallest real loop first.

- **3.1** A "fighting game" **genre skill** (vs. the current third/first/top-down *level* genres): a
  1v1 arena framing, two pawns, a round.
- **3.2** **GAS** scaffold: health/attributes, a basic attack ability, hit detection, a health bar.
- **3.3** One signature move per character (from the prompt) as a GAS ability + cue.
- **3.4** A meter system (the prompt's Soul Fracture Wrath/Sorrow) as two attributes + UI.
- **3.5** A basic AI opponent (State Tree) that approaches and attacks.
- **3.6** Win/lose + round flow.

**Exit:** two characters fight a round with health, one special, and a win condition. *Now it's a game.*

---

## Part 7 — Phase 4: story, audio, cinematics

- **4.1** Parse acts/branches/endings from the prompt into a story graph.
- **4.2** Dialogue (UMG) between fights; choice → alliance flags (Game Instance + USaveGame).
- **4.3** AI-written, voiced NPC lines (**ElevenLabs** — skill exists) + MetaSounds music/SFX.
- **4.4** A **Sequencer** finisher/intro cutscene, AI-staged.
- **4.5** Multiple arenas (Phase 3 of NEXTGEN_ROADMAP: PCG + landscapes) for the acts.

**Exit:** a 3-fight slice with dialogue, choices that change targeting, and one voiced cutscene.

---

## Part 8 — Phase 5: the AAA agent crew + ship

- **5.1** Specialist agents (environment / lighting / character / combat-designer / narrative / audio /
  QA) orchestrated by an art-director critic — the multi-agent leap.
- **5.2** Vision critic scoring Movie-Render-Queue stills vs reference rubrics; overnight iteration.
- **5.3** Performance (LODs, Nanite/Lumen scalability), packaging, store + compliance.

**Exit:** a small, polished, *shippable* slice produced largely autonomously.

---

## Part 9 — Honest ceiling

*Ashenveil Chronicles* in full is ~50–200 person-years of bespoke AAA work; **we will not literally
build it.** What this plan delivers is the **system** that turns a prompt into a *real, original,
modern-looking, playable* game — a polished vertical slice (one arena, two characters, one fight, one
cutscene) that *feels* next-gen — and the agent loop to keep deepening it. The discipline is what gets
us there: **fix the foundation (Phase 0), verify every step in-engine, micro-goal by micro-goal.**

---

## Right now — the next micro-goal

**Phase 0.1: persist deletions** — turn on the editor-in-the-loop (`WebControl.StartServer`;
`playsmith unreal check` → "ON") and re-run a dress; verify the object count drops and the template
demo clears. If staying headless, implement external-actor-package deletion. *Everything else waits on
this.*

*(Companion docs: [`NEXTGEN_ROADMAP.md`](NEXTGEN_ROADMAP.md) — the fidelity-lever view; this file —
the micro-goal execution plan grounded in the stress-test findings.)*
