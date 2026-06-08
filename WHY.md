# WHY.md — why Playsmith exists, why it's different, and the discipline that keeps it alive

> Read this if you're wondering "isn't this just another AI tool that'll fail?" — a fair
> question. This doc is the strategic spine of the project. Contributors: this explains why
> the scope is *deliberately* narrow. Founder: re-read this whenever you're tempted to widen it.
>
> **This is a re-founding doc.** Playsmith does **not** yet produce polished games. What follows
> is the rationale for *how it intends to get there* — and the discipline required to not fail on
> the way. The canonical state of the project lives in [`CLAUDE.md`](./CLAUDE.md) §0; the public
> overview is [`README.md`](./README.md). If anything here contradicts `CLAUDE.md`, `CLAUDE.md` wins.

## The honest starting point: why we re-founded

Playsmith began Godot-first, 2D-first, "any local LLM, fully headless." It was a clean,
disciplined architecture — and it produced **tech demos, not games**. The reason is worth
stating plainly because it's the whole thesis of the re-founding:

> The old loop optimized for *"compiles + `player_on_floor=true`."* It never optimized for
> content, level design, or game feel. So it built things that *ran* and *asserted true* and
> were *boring*. Measured against "is this actually a game someone would play," the output
> topped out at roughly **2%.**

You can't get to a good game by stacking more structural assertions. "It runs" and "it's good"
are different problems, and we were only ever solving the first one. The fix is three moves,
all made deliberately:

1. **Unreal Engine 5.x, not Godot.** UE ships world-class templates, lighting, animation, and a
   rendering bar that 2D-from-primitives can't touch. The hard part of "feels like a real game"
   is largely *already solved* inside the engine — if we start from the right place.
2. **Build ON shipping templates, never from an empty scene.** Every game starts from a real,
   playable, lit, animated UE template (`TP_ThirdPersonBP` / `TP_FirstPersonBP` / `TP_TopDownBP`).
   The LLM is a **director that dresses and tunes** an already-good game — not a from-scratch
   level builder. This is the single biggest quality lever we have.
3. **A real director→critic quality loop.** A critic agent scores **rendered screenshots + real
   PIE metrics** against a quality rubric and sends work back — layered *on top of* the headless
   `PLAYSMITH_ASSERT` reality loop, not replacing it. We finally measure the thing we actually care
   about.

Everything below is the strategy that makes this bet survivable.

## Why most AI tools fail (and how Playsmith dodges each)

It's rarely the technology. AI tools die from four predictable traps:

1. **The thin-wrapper trap** — a prompt box over someone else's model. The model maker
   absorbs the feature and the tool becomes pointless.
2. **The demo-magic trap** — a great 30-second video that collapses at the "last 30%" of
   real use.
3. **The economics trap** — inference costs more than users will pay, or the business *is* the
   inference bill.
4. **The hype-wave trap** — riding a buzzword that crests and recedes.

Playsmith is built to avoid three of these by **construction**, not by hope:

- **Not a wrapper.** Our value is the orchestration a model can't do alone: driving the Unreal
  editor, cloning and dressing templates, the run→render→critique→fix reality loop, the genre
  skills, and the path to a packaged build. When base models improve, Playsmith gets *better*,
  not obsolete. Improving models are a tailwind, not a threat.
- **Not business-model-bound to inference.** Playsmith is open source and self-hostable. There is
  no per-user hosted backend that has to make margin on tokens. You bring your own model access;
  we monetize nothing on inference. (More on the honest cost trade-off below.)
- **Not hype-locked.** The output is a real, durable artifact — an editable UE project on your
  disk — useful regardless of which AI trend is in fashion.

The demo-magic trap (#2) is the one we *don't* get for free — it's the real risk, and the entire
re-founding (templates + critic loop) exists to fight it. See "The honest risks."

## The market gap: where everyone else stops

This is the part that justifies the whole bet, told honestly:

- **The best-funded prompt-to-game tools only reliably nail *simple 2D.*** That's a real
  achievement and a real market — but it's a *different* market. Nobody has shown reliable,
  prompt-to-**polished-3D** generation.
- **Epic's own AI positioning is an in-editor *assistant*, not an auto-generator.** The engine
  vendor with the most to gain is helping you author faster — not turning a sentence into a
  finished level. That's a signal about how hard the real thing is, and a lane they aren't taking.
- **"World model" / neural-frame demos (Genie, Oasis) are not editable projects.** They generate
  ephemeral frames, not a UE project you can open, change, and ship. Impressive, and orthogonal to
  us.

So the emptiest, hardest part of the map is: **a real, editable, polished 3D game in a real engine,
generated from a prompt, that you own and can ship.** That's where Playsmith plants its flag —
*precisely because* it's empty and hard. Easy and crowded is not a moat.

> We are not claiming we've reached it. We're claiming it's the right hill, and that templates +
> a critic loop are the credible path up it. The 2% number is our reminder of how far there is to go.

## The structural moats

1. **You own the output, and it outlives the tool.** Closed competitors give you output locked to
   their servers, or ephemeral neural video. Playsmith writes a real Unreal project to your disk
   that you can open in the editor, change, and ship even if Playsmith vanishes tomorrow. The value
   persists independent of the tool. This is the opposite of lock-in.

2. **The template foundation.** Quality comes from *building on a shipping game*, not from a model
   inventing a game from nothing. This is both our biggest quality lever and a moat: it encodes a
   discipline ("never start from an empty scene") that competitors selling "type a sentence, get a
   world" are structurally disincentivized to adopt, because it's less magical to demo and harder
   than it looks to do well.

3. **The director/critic reality loop.** The hard, unglamorous engineering — render a real frame,
   read real PIE metrics, score against a rubric, send work back — is the thing that separates a
   demo from a game. It's not a prompt; it's a system. That system is the product.

4. **Models are a tailwind, not a threat.** A thin wrapper dies when the next model ships.
   Playsmith's hard part was never token generation — it's directing an engine, judging rendered
   output, and getting to a packaged build. Better frontier models make every Playsmith game better
   without making Playsmith redundant.

## The fourth moat (the compounding one): open + community skills

A single tool is copyable. A **library of community-authored game skills** — plus a community of
people sharing the games they made — is a network effect. ComfyUI's moat isn't its node engine;
it's the thousands of community workflows. Playsmith's equivalent is the skills library, served
through a **secure community marketplace**. This is the durable, long-term moat *if we earn it* —
which means the skill format must stay open (the SKILL.md standard), contributing a skill must be
easy, and the marketplace must be safe to install from. Apache-2.0 keeps it all unencumbered.

## The positioning: own the intersection, not a single feature

Weak differentiation is "we do one thing 10% better" — a funded incumbent just copies it.
Playsmith's differentiation is an **intersection no incumbent can occupy**:

> **open + self-hostable + any-engine + real, editable, *polished* UE games that ship + community skills**

This is defensible because incumbents are *structurally* blocked from key axes:
- A hosted platform **cannot** become "open + self-hostable" without breaking its business model.
- A single-engine vendor's AI **cannot** become "any-engine," and (per their own positioning)
  isn't trying to be an auto-generator.
- A world-model demo **cannot** hand you an editable, shippable project — that's a different
  paradigm.

We win on the axes they can't follow. We do **not** try to out-polish them on UX with their
funding — that's their game, not ours.

## The pillars (in priority order)

These are the same four in `CLAUDE.md`, restated as *why* each is ranked where it is:

1. **Shippable real, polished UE games.** The reason to exist. Everything else is in service of
   this. A runnable, *good* slice that ships beats an ambitious one that doesn't.
2. **Quality first, with tiered models.** A frontier model drives the director/critic reasoning;
   local models do cheap sub-steps. **This deliberately relaxes the old "any local LLM, fully
   headless" purity — and it should be uncomfortable.** Here's the honest trade: trying to honor
   *both* "any local model, no GPU rendering" *and* "polished games" at the same time is *exactly
   why the output was 2%.* You cannot judge quality you never render, and a 7B local model cannot
   direct a polished 3D level. We chose quality. Self-hostable remains a goal; quality is the hill
   we die on.
3. **Any-engine.** Unreal now, behind the `EngineAdapter` abstraction so more engines can slot in.
   Abstraction is cheap insurance; premature multi-engine is scope creep. One engine, done well.
4. **Open.** Apache-2.0, community skills, no lock-in. This is the compounding moat and the reason
   contributors show up. (Note: Unreal itself ships under Epic's EULA and carries royalties on
   shipped revenue — Playsmith's code is Apache-2.0, but builds made *with* UE inherit UE's terms.
   We surface this honestly; we don't paper over it.)

## The honest risks (the ways we actually could fail)

1. **The quality bar is genuinely hard — the #1 killer.** "Polished 3D from a prompt" is the
   emptiest part of the market *because nobody's nailed it.* That's the opportunity and the danger.
   If the director/critic loop can't reliably clear the rubric, we've built a slower way to make a
   tech demo. Mitigations: build on templates so we start from "already good"; scope to one genre
   first; let the critic loop self-correct against real rendered output; keep expectations honest.
   **We must produce one genuinely good, playable UE game before any breadth.**

2. **Unreal complexity and slow iteration.** A source-built UE editor boots slowly (~60s warm),
   maps and assets are binary (must be authored through the editor / Python API / a pinned MCP,
   never as text), and the toolchain is heavy. This makes the inner loop slow and the engineering
   fiddly. Mitigation: invest in the harness once, reuse it across all three genres; never churn
   the shader DDC with repeated hard kills.

3. **Cost and the "not pure-local" reality.** The director/critic need a frontier model
   (`ANTHROPIC_API_KEY`) and a GPU running the editor to render. That's real money and real
   hardware — a deliberate departure from the original pure-local promise. We're betting the
   quality is worth it, but it narrows who can run the full loop, and we should say so plainly.

4. **Template and asset licensing.** Building on UE templates and any generated/placeholder assets
   means license hygiene matters: UE EULA + royalties, template terms, and never reproducing
   copyrighted game IP. We audit deps against Apache-2.0 and surface UE's terms rather than hide them.

5. **Scope creep / ambition.** Five genres at 2% is worse than one genre that's actually fun.
   Serving every engine, dimension, and audience at once means doing all of them badly. The grand
   vision is the *destination*; the narrow first slice is the *vehicle that survives long enough to
   reach it.* This is the discipline this whole doc exists to protect.

6. **Distribution.** Even a great OSS tool dies unseen. The launch + community plan is real work,
   not an afterthought.

## What "success" means here (a lower, saner bar)

Playsmith is open source, not a winner-take-all startup. Success is **not** beating the funded
prompt-to-game platforms or needing an exit. Success is: **one Unreal scene that is genuinely,
visibly polished** — proof the loop works — then a few thousand GitHub stars, an active community,
and a steady trickle of people shipping real games they made with Playsmith. That bar is
achievable, and chasing it (instead of a billion-dollar outcome) keeps the project honest and alive.

## What has to stay true (the discipline rules)

If we hold these, Playsmith is not "another failed AI tool." If we break them, it becomes one.

1. **Build ON a template — never from an empty scene.** That's the old 2% path. The foundation is
   the quality.
2. **Always produce a real, owned, editable artifact.** Never hide the game behind a black box.
3. **Close the reality loop.** Run it, render it, read the metrics, let the critic judge against
   the rubric — then self-correct on what *actually happened*, not on what the code "should" do.
   "It compiles" is not "it's good," and we never again confuse the two.
4. **Nail ONE genre excellently before going wide.** Depth before breadth. Always. Prove
   third-person first; first-person and top-down ride the same rails.
5. **Don't chase world-models.** Our output is an editable UE project, not ephemeral neural frames.
   Different paradigm, different doc.
6. **Don't mass-submit near-identical games to stores.** Apple 4.2.6 and Google's repetitive-content
   rules reject it, and it would harm users. Publishing means shipping *a polished game*, with
   guided submission — not spamming stores.
7. **Keep the skill format open and the marketplace safe.** Interoperability and trust are both
   features and moats.

## The bottom line

We can't promise success — no one can, and anyone who does is selling something. We're also not
pretending we've arrived: today Playsmith makes tech demos, and the whole point of the re-founding
is to change that. But Playsmith won't fail for the reasons most AI tools fail — it sidesteps the
wrapper trap, the inference-business trap, and the lock-in trap by design. It can only fail on
**output quality or lost discipline** — and the re-founding aims both squarely: templates and the
critic loop attack quality, and these discipline rules attack drift. Both are **ours to control.**
That's the smartest possible way to make this bet.
