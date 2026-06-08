# Build Plans — the whole journey, one page

Playsmith is built in phases, each answering **one question** and ending in something demoable. The order is
deliberate (`WHY.md` rule #3: *depth before breadth, always*). This page is the map; each phase has its own
step-by-step, paste-a-prompt build plan.

| Phase | The one question it answers | Build plan | Status |
|---|---|---|---|
| **0** | Can the plumbing turn a prompt into a real Godot project? | [`BUILD_PLAN.md`](../BUILD_PLAN.md) | ✅ code-complete (live run needs local Godot + model) |
| **1** | Can a local model make **one** 2D genre that's genuinely *good* and shippable? | [`docs/BUILD_PLAN_PHASE1.md`](BUILD_PLAN_PHASE1.md) | ▶ next |
| **launch** | Is it worth showing the world? | [`docs/LAUNCH.md`](LAUNCH.md) | after Phase 1 DoD |
| **2** | Can we add breadth (3D, a 2nd engine, a marketplace) without breaking the discipline? | [`docs/BUILD_PLAN_PHASE2.md`](BUILD_PLAN_PHASE2.md) | gated on Phase 1 |
| **3** | Can a user ship to the big stores **responsibly**? | [`docs/BUILD_PLAN_PHASE3.md`](BUILD_PLAN_PHASE3.md) | gated on Phase 2 |
| **beyond** | How does it *last*? | tail of [`BUILD_PLAN_PHASE3.md`](BUILD_PLAN_PHASE3.md) | community + curation + quality |

## The through-line

```
Phase 0  plumbing                prompt → real Godot project (route→scaffold→generate→reality-loop→run→export)
   │     [done]
Phase 1  ONE genre, genuinely good   + any model (local/cloud) + real art + edit-by-NL + publish to itch
   │     [the launch]                 = the version worth launching
Phase 2  breadth, earned             3D in Godot → skill marketplace (safe) → Unreal track (experimental)
   │
Phase 3  ship to big stores          desktop → Steam → Android → iOS, with disclosures, guided manual submission
   │
beyond   it lasts                    grow the community skill library (the compounding moat); deepen, don't sprawl
```

## The spine that never bends (the `WHY.md` discipline rules)

These hold in **every** phase. If they hold, Playsmith is not "another failed AI tool"; if they break, it becomes one.

1. **Always produce a real, owned, editable artifact.** Never hide the game behind a black box.
2. **Stay local-first.** Cloud is an optional fallback, never a requirement.
3. **Nail ONE game type excellently before going wide.** Depth before breadth. Always.
4. **Keep the skill format open** (`SKILL.md`). Interoperability is a feature and a moat.
5. **Fail cheap and early.** Each phase is an experiment with a checkpoint; if a phase says "no," we learned it cheaply.

## Permanent non-goals (true forever, regardless of phase)

- ❌ A hosted cloud backend as *the product* (kills the local-first economics moat).
- ❌ The world-model / real-time neural-video paradigm (not an editable, owned artifact).
- ❌ Auto-mass-submission of near-identical games to stores (platform rules; harms users).
- ❌ Hiding the code or locking in the output.
- ❌ Requiring cloud / breaking local-first.

## How to use these plans

Open the repo in Claude Code (it auto-reads `CLAUDE.md`). Go to the current phase's build plan, paste each
step's prompt one at a time, verify the checkpoint, `git commit`, and move on. Don't jump phases — each one
enables the next, and the gates exist on purpose.
