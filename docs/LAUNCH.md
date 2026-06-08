# Launch Playbook (Phase 1)

This is the launch plan for the version worth launching — the **Phase 1** build (referenced by
`docs/ROADMAP.md`). It is intentionally a Phase-1 doc, not a Phase-0 one: a colored-rectangle tech demo
is not launch-worthy. A 2D game that has **real art, edits by natural language, runs with no errors, and
ships to itch.io — made by the user's own local model** — is.

`WHY.md` is blunt about the trap we must avoid here: the **demo-magic trap** (#2) — a great 30-second
video that collapses at the "last 30%." So this playbook optimizes for *honest* magic, not hype.

---

## When to launch

Only after **Phase 1's Definition of Done** is met (see `docs/BUILD_PLAN_PHASE1.md`):
- prompt → runnable 2D platformer **or** short dialogue/story game, no errors;
- real art in it (AI-generated sprites or user-supplied), not just placeholders;
- `playsmith edit "<change>"` works and stays runnable;
- `export --target web` + `publish --itch` put it online;
- the project opens and edits in the Godot editor.

If any of those is shaky, the launch will read as demo-magic. Wait.

---

## The one artifact that matters: the demo

A **60–90 second screen recording**, no cuts that hide failure:
`prompt → routed skill → real art appears → playsmith edit changes it live → export → it's playable on itch`.

Show the reality loop briefly (run → error → fix → run clean) — the *honesty* is the differentiator. Show
the generated project folder open in the Godot editor — *you own this*. End on the itch.io URL.

---

## The message (lead with the intersection, not "AI makes games")

The moat is **open + local + any-engine + real-shippable + you own it**. Lead there:

> "Type a prompt. Your own local model builds a **real, editable Godot game** — and ships it to itch.io in
> minutes. No cloud required, no lock-in, the project is yours."

Do **not** lead with "AI generates games" (crowded, and invites the AAA/world-model comparison we lose).
Lead with **ownership + local + shippable**. Be explicit about what it is *not* yet (no 3D/Unreal/AAA) — that
candor builds trust and pre-empts the "but can it do GTA" disappointment.

---

## Channels (in rough order)

1. **GitHub** — the README is the landing page (badges, topics, the demo GIF at the top). Done: description +
   topics. Add: CI + license badges, the demo GIF, 2–3 example games.
2. **Show HN** ("Show HN: Playsmith – prompt → a real Godot game your local model makes, shipped to itch").
3. **Reddit** — r/godot, r/gamedev, r/LocalLLaMA (the local-model angle plays especially well here).
4. **itch.io devlog** + the example games published *with* Playsmith (dogfood the publish pipeline).
5. **A short blog post** / X / Mastodon / Bluesky thread built around the demo GIF.
6. **A Discord** for the community (the moat is people; give them a home on day one).

---

## The viral loop (from ROADMAP "always-on")

- A **game jam** within ~1 month of launch — "make + ship a game with Playsmith." This is the natural growth
  engine and the best stress test of the quality bar.
- A **showcase gallery** of games made with Playsmith, and a **"Made with Playsmith"** badge.
- Fast issue response (<24h target); treat early contributors as the seed of the skill-library moat.

---

## Pre-launch checklist

- [ ] CI is green; QUICKSTART works from zero on a clean machine (have someone else try it).
- [ ] `LICENSE` is complete (Apache-2.0, year/holder filled — Phase 1 Step 0).
- [ ] `CONTRIBUTING.md` + `docs/CONTRIBUTING_SKILLS.md` + `docs/SKILL_SPEC.md` exist (Phase 1 Step 6).
- [ ] Issue templates + a `CODE_OF_CONDUCT.md`.
- [ ] The demo GIF is recorded and in the README.
- [ ] 2–3 example games exist in a gallery and are published to itch.
- [ ] README/WHY clearly state what's in scope (2D, local-or-cloud) and what isn't yet (3D/Unreal/AAA).

---

## Anti-goals at launch (don't break the trust)

- ❌ Don't promise 3D / Unreal / "realistic/AAA/GTA" — not ready; promising it is the demo-magic trap.
- ❌ Don't claim "no cleanup needed," especially for art. Set honest expectations (`WHY.md` risk #1).
- ❌ Don't compete on UX polish against funded incumbents — win on the axes they can't follow (open/local/yours).
- ❌ Don't hide failures in the demo. The reality loop *is* the story.

---

## What success looks like (kept saner on purpose)

Per `WHY.md`: a few thousand GitHub stars, an active community, and a steady trickle of people shipping games
they made with Playsmith. Not an exit, not beating a funded incumbent. That bar is achievable, and aiming at it
is what keeps the project honest and alive.
