# WHY.md — why Playsmith exists, why it's different, and the discipline that keeps it alive

> Read this if you're wondering "isn't this just another AI tool that'll fail?" — a fair
> question. This doc is the strategic spine of the project. Contributors: this explains why
> the scope is *deliberately* narrow. Founder: re-read this whenever you're tempted to widen it.

## Why most AI tools fail (and how Playsmith dodges each)

It's rarely the technology. AI tools die from four predictable traps:

1. **The thin-wrapper trap** — a prompt box over someone else's model. The model maker
   absorbs the feature and the tool becomes pointless.
2. **The demo-magic trap** — a great 30-second video that collapses at the "last 30%" of
   real use.
3. **The economics trap** — cloud inference costs more than users will pay. ("Inference
   cannot be the business model.")
4. **The hype-wave trap** — riding a buzzword that crests and recedes.

Playsmith is built to avoid three of these by **construction**, not by hope:

- **Not a wrapper.** Our value is the orchestration a model can't do alone: driving the
  engine, the run→screenshot→fix reality loop, the asset pipeline, the genre skills, and the
  path to the store. When base models improve, Playsmith gets *better*, not obsolete. Improving
  models are a tailwind, not a threat.
- **Not cloud-cost-bound.** Local-first means near-zero marginal cost per user. That's why an
  open-source local tool can grow virally with no burn rate — the ComfyUI/Ollama model, not
  the hosted-platform model.
- **Not hype-locked.** The output is a real, durable artifact (see below), useful regardless
  of which AI trend is in fashion.

The demo-magic trap (#2) is the one we *don't* get for free — it's the real risk, and we
fight it with discipline (see "What has to stay true").

## The three structural moats

1. **You own the output, and it outlives the tool.** Closed competitors give you output
   locked to their servers, or ephemeral neural video. Playsmith writes a real engine project
   to your disk that you can open, edit, and ship even if Playsmith vanishes tomorrow. The
   value persists independent of the tool. This is the opposite of lock-in.

2. **Models are a tailwind, not a threat.** A thin wrapper dies when the next model ships.
   Playsmith's hard part was never token generation — it's integration with engines, assets,
   and stores. Better models make every Playsmith game better without making Playsmith
   redundant.

3. **Local-first economics.** No per-user inference bill. Growth isn't throttled by a burn
   rate. Open source + local is a sustainable shape; cloud-only-at-a-loss is not.

## The positioning: own the intersection, not a single feature

Weak differentiation is "we do one thing 10% better" — a funded incumbent just copies it.
Playsmith's differentiation is an **intersection no incumbent can occupy**:

> **open + local + any-engine + real-shippable + integrated assets + publish**

This is defensible because the incumbents are *structurally* blocked from key axes:
- A hosted platform **cannot** become "open + local" without destroying its business model.
- A single-engine vendor's AI **cannot** become "any-engine."
- A world-model demo **cannot** hand you an editable, shippable project — that's a different
  paradigm.

We win on the axes they can't follow. We do **not** try to out-polish them on UX with their
funding — that's their game, not ours.

## The fourth moat (the compounding one): community skills

A single tool is copyable. A **library of community-authored game skills** plus a community
of people sharing the games they made is a network effect. ComfyUI's moat isn't its node
engine — it's the thousands of community workflows. Playsmith's equivalent is the skills
library. This is the durable, long-term moat *if we earn it* — which means the skill format
must stay open (SKILL.md standard) and contributing a skill must be easy.

## The honest risks (the ways we actually could fail)

1. **The quality gap / "70% problem"** — *the #1 killer.* If local models + AI assets produce
   games that are *almost* there but need so much cleanup the magic dies, people churn.
   Mitigations: scope tight; lean on deterministic scaffolding (e.g. the hand-written
   `player.gd` template instead of asking the model to invent movement); use the reality loop
   to self-correct; cloud fallback for hard steps; honest expectations. **The MVP must produce
   one genuinely good, playable game type before any breadth.**

2. **Scope creep / ambition** — trying to serve every engine, genre, dimension, and audience
   at once means doing all of them badly. The grand vision is the *destination*; the narrow
   MVP is the *vehicle that survives long enough to reach it*. This is the discipline this
   whole doc exists to protect.

3. **Distribution** — even a great OSS tool dies unseen. The launch + community plan is real
   work, not an afterthought.

4. **Incumbent pace** — funded competitors ship fast. We don't beat them on polish; we beat
   them by being the thing they can't be (open, local, yours).

## What "success" means here (a lower, saner bar)

Playsmith is open source, not a winner-take-all startup. Success is **not** beating Rosebud or
needing an exit. Success is: a few thousand GitHub stars, an active community, and a steady
trickle of people shipping games they made with Playsmith. That bar is achievable, and
chasing it (instead of a billion-dollar outcome) keeps the project honest and alive.

## What has to stay true (the discipline rules)

If we hold these, Playsmith is not "another failed AI tool." If we break them, it becomes one.

1. **Always produce a real, owned, editable artifact.** Never hide the game behind a black box.
2. **Stay local-first.** Cloud is an optional fallback, never a requirement.
3. **Nail ONE game type excellently before going wide.** Depth before breadth. Always.
4. **Keep the skill format open.** Interoperability is a feature and a moat.
5. **Fail cheap and early.** Phase 0 is a 2–6 week experiment answering one question: *can this
   make one good game locally?* If yes, we have something real. If no, we learned it cheaply.

## The bottom line

We can't promise success — no one can, and anyone who does is selling something. But Playsmith
won't fail for the reasons most AI tools fail: it sidesteps the wrapper trap, the economics
trap, and the lock-in trap by design. It can only fail on output quality or lost discipline —
and both are **ours to control**, and both get tested cheaply in Phase 0. That's the smartest
possible way to make this bet.
