# Build Plan — Phase 3 (Ship to the big stores — responsibly)

Continuation of `docs/BUILD_PLAN_PHASE2.md`. Phase 3 completes the **"and ships it"** pillar: from a
generated game to a store-ready build for Steam and mobile, with the **right disclosures generated and the
user guided through manual submission**. The hard rule from CLAUDE.md §8 governs this entire phase:

> **Guided, compliant, single-game submission — never auto-mass-submission.** We help a user ship *a*
> polished game, with correct disclosures; we never spam stores with near-identical games, and we never
> help defeat store review or AI-disclosure requirements.

> Same rhythm: paste a step, verify the checkpoint, commit.

---

## READ THIS FIRST — the scope decision

Phase 3 is where the publish pipeline grows teeth, and where **policy, not capability, is the constraint**.
The platforms (Apple 4.2.6, Google "repetitive content") explicitly reject mass-generated/near-identical
submissions; pretending otherwise would harm users and get them banned. So Phase 3's value is **compliance as
a feature**: do the export, generate the disclosure, surface the rule, and hand off a clean manual submission.

**Phase 3 is in scope:**
1. Desktop export hardening (Windows / macOS / Linux) — the packaging foundation for stores.
2. **Steam** publishing (SteamPipe / steamcmd) + an **AI-disclosure helper**.
3. **Android** export + signing + the Google "repetitive content" guardrail.
4. **iOS** export (requires macOS/Xcode) — guided, with Apple 4.2.6/4.3 warnings.
5. A consolidated **compliance helper suite** + an **age-rating (IARC)** questionnaire helper.

**Explicitly NOT in Phase 3 (permanent non-goals):**
- ❌ Auto-mass-submitting near-identical games to any store — **permanently out** (Apple 4.2.6, Google
  repetitive content; CLAUDE.md §8).
- ❌ Auto-publishing to a store's default/live channel without an explicit human gate.
- ❌ Helping bypass or fake store review, age rating, or AI-content disclosure.
- ❌ Hosted SaaS, world-model — **permanently out** (`WHY.md`).

---

## The quality bar for Phase 3

Phase 3 is "good" when a user can take one finished game and:
- produce a **signed, store-ready build** for Steam and/or Android (and iOS on macOS);
- get the **correct disclosures auto-generated** (Steam AI-content; the right platform warnings surfaced);
- run `playsmith publish --check` and see exactly which policies apply and what they must do;
- be **guided** through the final manual submission — never auto-submitted.

---

## Prerequisites delta (beyond Phase 2)

- **Godot export templates** for desktop, Android, and iOS (HTML5 already covered in Phase 0/1).
- **(Optional) steamcmd / SteamPipe** + a Steamworks partner account for the Steam step.
- **(Optional) Android SDK + a signing keystore** for the Android step.
- **(Optional) macOS + Xcode** for the iOS step (Apple requires it; cannot be done from Linux/Windows).

---

## Step 0 — Orient + doc hygiene (no features)
**Paste:**
> Read `CLAUDE.md`, `WHY.md`, `docs/ARCHITECTURE.md` §6, `docs/ROADMAP.md`, and this file. In 6 bullets,
> confirm the Phase 3 scope and the **permanent non-goals** (especially: no auto-mass-submission, no
> auto-publish to a live channel, guided manual submission only). Ensure `docs/ARCHITECTURE.md` §6 lists the
> full compliance-helper set. Commit as "docs: Phase 3 scope". No features.

**Checkpoint:** docs agree; the no-mass-submission rule is unmistakable; no code changed.

---

## Step 1 — Desktop export targets (store-packaging foundation)
**Paste:**
> Extend `ExportTarget` and the GodotAdapter export path for Windows, macOS, and Linux, with generated
> export presets per target and `playsmith export --target windows|mac|linux`. Document (not automate) the
> code-signing / notarization steps each store needs, surfaced as hints. Reuse the Phase 0 web-export pattern.
> Tests with the godot binary mocked, mirroring `tests/test_godot_adapter.py`.

**Checkpoint:** `playsmith export --target linux` (and win/mac on the right host) produces a runnable desktop
build; signing requirements are surfaced as guidance.

---

## Step 2 — Steam publishing + AI-disclosure helper
**Paste:**
> Implement Steam publishing in `playsmith/publish/`: `playsmith publish --steam <appid> [--branch beta]`
> wrapping steamcmd / SteamPipe to upload a depot build to a **non-default branch by default** (never auto-push
> to the live/default branch). Before upload, generate a **Steam AI-content disclosure** via a helper that asks
> whether assets are pre-generated vs live-generated and notes Valve's Jan-2026 rewrite (dev tools like code
> assistants are *exempt*; player-facing generated assets are *not*). steamcmd is optional — fail with a clear
> install hint. Tests with the steamcmd subprocess mocked.

**Checkpoint:** with steamcmd configured, a build uploads to a beta branch and a correct AI-disclosure draft is
generated; promoting to live remains a deliberate human action outside the tool.

---

## Step 3 — Android export + signing + repetitive-content guardrail
**Paste:**
> Add an Android export path (Godot Android export → AAB/APK) with a **keystore signing helper**
> (`playsmith export --target android`, prompting for/locating a keystore). Before any submission guidance,
> surface the **Google Play "repetitive content"** policy (mass near-identical games are removed) and confirm
> this is a single, distinct game. Submission itself is manual/guided, never automated. Tests with the
> export/sign subprocess mocked.

**Checkpoint:** a signed AAB/APK is produced; the repetitive-content rule is shown; the tool guides but does not
auto-submit.

---

## Step 4 — iOS export (guided; macOS only)
**Paste:**
> Add an iOS export path (Godot iOS export → an Xcode project handoff) usable on macOS. Surface Apple Guideline
> **4.2.6** (app-generation/template submissions are rejected unless submitted by the content provider) and
> **4.3** (spam) clearly before guiding the user to Xcode/App Store Connect for the manual submission. Detect a
> non-macOS host and explain the requirement instead of failing obscurely. Tests for the host-detection + guidance
> paths.

**Checkpoint:** on macOS, an Xcode project is produced with the Apple-policy warnings surfaced; on other hosts,
the requirement is explained cleanly.

---

## Step 5 — Compliance suite + age rating (consolidate)
**Paste:**
> Consolidate every compliance helper into `playsmith publish --check [--project <dir>]`, printing exactly which
> policies apply to this project/target: Steam AI-content disclosure, Apple 4.2.6/4.3, Google repetitive-content,
> the Unreal royalty estimate (if the Unreal track was used), and the **AI-asset copyright caveat** (per the US
> Copyright Office's March-2025 guidance, purely AI-generated assets have limited protection). Add an **age-rating
> (IARC) questionnaire helper** that produces a draft rating answer set. All advisory + guiding — never a
> substitute for the developer's own submission. Tests for the rule-selection logic per target.

**Checkpoint:** `playsmith publish --check` gives a correct, target-specific compliance + age-rating briefing for
a real project.

---

## Step 6 — Polish, docs, demo
**Paste:**
> Tighten UX/errors across the publish surfaces. Update `docs/QUICKSTART.md` and `docs/ROADMAP.md` (check Phase 3
> boxes truly done). Record a demo: one game taken from prompt → store-ready build (Steam beta branch and/or signed
> Android) → `publish --check` disclosures → guided handoff. Reaffirm the no-mass-submission stance in the README.

**Checkpoint:** the docs walk a user from a finished game to a compliant, store-ready build with disclosures, and
the manual-submission, single-game stance is explicit everywhere.

---

## Phase 3 Definition of Done
A user can produce a store-ready mobile/Steam build with the right disclosures generated, guided through manual
submission (not auto-spamming). The "and ships it" pillar is complete across web → desktop → Steam → mobile,
responsibly.

---

# After Phase 3 — the destination, and the permanent guardrails

There is no "Phase 4 sprint" with a fixed checklist — past Phase 3 the work is mostly **community, curation, and
quality**, which is exactly the compounding moat `WHY.md` identifies. The roadmap's grand vision (more engines,
richer genres including a fuller "story mode," better generated art, broader publishing) is pursued only by the
same rule that got us here: **depth before breadth, one proven axis at a time.**

**What "more" looks like, in priority order, *if earned*:**
1. **Grow the skill library + community** — the network effect. More curated, validated, secure genre skills from
   contributors; a showcase gallery of games people shipped; a "made with Playsmith" badge. This is the moat.
2. **Deepen existing genres** before adding new ones — make the 2D platformer, the story game, and the 3D
   platformer *excellent* and editable, not just runnable.
3. **Better art + cleanup tooling** — close the AI-asset "70% gap" (topology/UV/rig helpers for 3D; style
   consistency for 2D), since asset quality is the #1 churn risk.
4. **More engines / genres** — only behind the stable `EngineAdapter` + `SKILL.md` contracts, and only once the
   current set is genuinely good.

**Permanent non-goals (true in every phase, forever):**
- ❌ A hosted cloud backend as *the product* (cloud stays an optional fallback — the economics moat).
- ❌ The world-model / real-time neural-video paradigm (it is not an owned, editable artifact).
- ❌ Auto-mass-submission of near-identical games to any store.
- ❌ Hiding the code or locking in the output. **Always produce a real, owned, editable artifact.**
- ❌ Requiring cloud, or breaking local-first.

**The success bar (from `WHY.md`, kept honest):** a few thousand GitHub stars, an active community, and a steady
trickle of people shipping games they made with Playsmith. Not a winner-take-all exit. Chasing that saner bar is
what keeps the project alive — and it is the same reason the scope was kept narrow at every phase above.

See `docs/LAUNCH.md` for the Phase-1 launch playbook and `docs/BUILD_PLANS.md` for the whole journey on one page.
