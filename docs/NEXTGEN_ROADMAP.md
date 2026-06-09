# Playsmith → Next-Gen: the road from "prototype" to modern, AAA-looking games

> Goal (the user's words): *"give us almost similar results like GTA 5 and other modern
> next-generational games."* This document is the honest, deep, phased plan to get as close to that
> as a prompt-to-game tool realistically can — and to be clear about where the ceiling is.

---

## 0. The honest premise (read this first)

**We will not literally produce GTA 5.** GTA 5 cost ~$265M and ~1,000+ people over ~5 years — bespoke
city modelling, mocap, writing, QA. No prompt-to-game tool will match that bespoke content or scale.

**But we can close most of the *perceived* gap**, because the things that make a game *look and feel*
next-gen are mostly **available to us for free**, and the work is **orchestration, not invention**:

- **Unreal Engine 5** ships the same renderer AAA studios use — Nanite, Lumen, Virtual Shadow Maps,
  TSR, hardware ray tracing. We're already on it.
- **Fab / Quixel Megascans** (free for use in Unreal) is thousands of *film-quality, photo-scanned*
  meshes, surfaces, and decals. **MetaHuman** (free) is photoreal characters. **Marketplace kits**
  give modular cities, interiors, vehicles, props.
- **AI** (what Playsmith is) can do the part humans spend the most time on: **choosing, placing,
  lighting, and tuning** that content into a coherent, playable, *original* game — and writing its
  quests, dialogue, music, and voice.

> **The #1 truth of this whole roadmap:** *fidelity comes from real assets + UE5 rendering, not from
> arranging primitives.* Today the director dresses a level with grey/coloured **prototype cubes**.
> Swapping that for **real assets** is the single biggest visible leap — Phase 1 — and everything
> else compounds on it.

**Reality constraints we design around:**
- **Hardware** — Lumen/Nanite + MetaHuman + crowds need a strong GPU. The dev box (RTX 3060) handles
  moderate scenes; large open worlds and cinematic renders want a bigger card or a **cloud render
  path**. Scalability settings must auto-tune per target.
- **Headless UE has real limits** (this session proved it): rendering arbitrary cameras, editing
  Blueprint components, and **World Partition persistence** are fragile in commandlets. An
  **editor-in-the-loop MCP** (a live UE editor the agent drives) is almost certainly required for
  reliable, high-fidelity authoring — see Phase 0.
- **Licensing & originality** — Fab/Megascans/MetaHuman are free *for Unreal use*; we must respect
  their terms, keep generated content **original** (no copyrighted IP/maps), and track provenance.

---

## 1. The five fidelity levers (the "why" behind every phase)

Everything below pulls one or more of these. Ranked by visible impact per unit effort:

1. **Real assets** — Megascans surfaces/props, Fab modular kits, MetaHuman characters. *The look.*
2. **UE5 rendering** — Nanite (film geometry), Lumen (real-time GI + reflections), VSM, TSR, ray
   tracing, post-process/color grading. *The lighting and material believability.*
3. **Procedural generation** — PCG framework, Landmass terrain, Water, foliage scatter. *Scale + density.*
4. **Living systems** — Mass AI crowds, Smart Objects, Chaos Vehicles, day/night, weather, audio
   zones. *The "alive" open-world feel.*
5. **AI content pipeline** — AI textures/PBR materials, (emerging) text-to-3D, AI narrative/quests,
   MetaSounds + AI music/SFX + voice (ElevenLabs). *Automation + originality at scale.*

---

## 2. Phase 0 — Foundation hardening (must precede the fidelity phases)

The current foundation can't *reliably* carry AAA content until these are fixed. Several are blockers
this session surfaced directly.

| Workstream | Why it blocks AAA | What "done" looks like |
|---|---|---|
| **World Partition persistence** | Re-dressing *stacks* objects (deletes don't persist) and the `-game` render appears to show stale state — so dressing changes aren't reliably reflected. | Dressing reliably **adds, replaces, and clears** actors across boots; the render shows exactly the saved level. Likely needs proper external-actor save/delete + data layers. |
| **Editor-in-the-loop MCP** | Commandlets can't render arbitrary cameras, edit BP components, or author reliably. AAA authoring needs a live editor. | A pinned UE MCP (e.g. a Remote-Control/MCP bridge) drives a running editor (GPU) for placement, materials, lighting, MetaHuman, Sequencer — replacing fragile headless scripts. |
| **Asset pipeline** | Real assets must be imported, deduped, licensed, referenced safely (never a bad ref). | A managed local **asset library** + import/registry; the director only references known-good, license-clean assets. |
| **Cinematic render (MRQ)** | HighResShot is a flat game frame; AAA stills/trailers need Movie Render Queue (anti-aliased, ray-traced, deterministic). | MRQ-based stills + short fly-through videos for previews, the store page, and the **vision critic**. |
| **Vision critic that actually scores fidelity** | Today's critic counts objects; it can't tell "looks AAA" from "looks like blocks." | Vision model scores MRQ stills against composition/material/lighting/density rubrics vs reference imagery; drives iteration. (Gateway image support already landed.) |
| **Reproducibility** | AAA pipelines need seeded, repeatable generation. | Seeded generation; a manifest capturing every asset + decision so a build is reproducible. |

**Recommendation:** do Phase 0 first. Without reliable persistence + a real authoring loop + cinematic
render + a fidelity-aware critic, the fancy phases produce things we can't reliably build or judge.

---

## 3. The fidelity phases

### Phase 1 — Real-asset dressing (the look leap) ⭐ highest ROI
Swap prototype primitives for real content. This alone moves output from "prototype" to "real game."
- Integrate **Fab / Quixel Megascans / Bridge**: a curated, license-clean library of surfaces,
  props, decals, and **modular environment kits** (ruins, sci-fi, urban, nature).
- Director **kit-bashes** modular pieces (snap/grid, sockets) + scatters Megascans props, instead of
  placing cubes. The theme system already chosen (frozen/volcanic/…) selects the asset set + palette.
- Enable **Nanite + Lumen + VSM + TSR** by default; auto-set scalability per GPU; add a tuned
  post-process volume (exposure, bloom, color grade) per theme.
- Replace flat tint materials with **Megascans PBR materials** (albedo/normal/roughness/displacement).
- **Deliverable:** a level that reads as a real environment (rock, foliage, architecture), correctly
  lit by Lumen — not coloured blocks.

### Phase 2 — Photoreal characters & animation
- **MetaHuman** integration: replace the mannequin; retarget the template's locomotion to MetaHuman.
- Character variety (faces, bodies, outfits); LOD'd background characters for crowds.
- **Control Rig** + an animation library; AI selects idle/locomotion/interaction sets per role.
- **Deliverable:** believable characters and a player avatar, not grey mannequins.

### Phase 3 — Procedural worlds at scale
- **PCG framework**: rule-based scatter of vegetation, debris, props, and structures by biome.
- **Landmass** landscapes + **Water** (rivers, oceans, moats); roads/paths; cliffs.
- **World Partition** with data layers + streaming for large, dense, varied spaces.
- **Deliverable:** big, populated, varied worlds — the open-world *scale* feel.

### Phase 4 — Living-world systems (the "GTA feel")
- **Mass AI + Smart Objects**: NPC crowds with routines (pedestrians, workers, guards).
- **Chaos Vehicles**: drivable cars; simple traffic.
- **Day/night** (Sun Position / dynamic sky), **weather**, ambient audio zones, interactables.
- Lightweight **objectives/economy/state** so the world *does* something.
- **Deliverable:** a world that feels alive and reactive.

### Phase 5 — Narrative, audio & cinematics
- **AI-driven narrative**: quests, branching dialogue, NPC lines (LLM-authored, structured, original).
- **MetaSounds** + AI-generated **music/SFX**; **ElevenLabs** voice for NPCs/narration (skill exists).
- **Sequencer** cutscenes — AI-directed camera, staging, pacing.
- **Deliverable:** a game with story, voice, music, and cutscenes.

### Phase 6 — The AAA agent crew + ship
- **Multi-agent specialists** (each a focused agent, orchestrated by an art-director/critic):
  environment artist · lighting artist · character artist · level designer · narrative designer ·
  audio designer · QA. (Playsmith already has the agent loop + critic to grow into this.)
- **Vision critic** scores MRQ stills/clips against AAA reference rubrics; **overnight iteration**
  passes refine until the bar is met.
- **Performance**: auto-LODs, Nanite/Lumen tuning, selective lighting bakes, profiling, per-platform
  scalability.
- **Packaging & store**: Steam/Epic/itch builds + compliance/AI-disclosure helpers.
- **Deliverable:** a shippable, optimized, modern-looking game produced largely autonomously.

---

## 4. Cross-cutting tracks (run alongside all phases)

- **Asset & license governance** — provenance tracking; originality checks; never reproduce IP/maps.
- **Compute & cost** — frontier-LLM budget controls; an optional **cloud render farm** for MRQ and big
  bakes; overnight batch scheduling.
- **Determinism** — seeded generation + a full build manifest (every asset + decision) for repeatable,
  auditable builds.
- **Quality rubric evolution** — from "object density/spread" toward **photoreal** rubrics: composition,
  framing, material believability, lighting mood, silhouette readability, content density vs reference.
- **Skills ecosystem** — community-authored genre/theme/asset-pack skills (the marketplace) so the
  asset library and dressing styles grow without core changes.

---

## 5. Where to start (concrete next 3 moves)

1. **Phase 0 persistence + editor MCP** — make dressing reliably persist/clear and author through a
   live editor. (Unblocks everything; fixes the issues this session hit.)
2. **Phase 1 real assets** — wire Fab/Megascans + Nanite/Lumen; director kit-bashes real kits. *This is
   the leap the user will actually see.*
3. **Phase 0 cinematic render + vision critic** — MRQ stills + a fidelity-scoring critic, so quality is
   measurable and the loop can chase it.

Everything after compounds on "real assets, reliably authored, judged by a critic that can see."

---

## 6. Honest risk register

- **We approximate the *look* and *systems* of AAA, not its bespoke content or scale.** Set
  expectations accordingly (and in marketing).
- **Headless UE is a ceiling** — an editor-in-the-loop MCP is likely mandatory for high fidelity.
- **AI 3D-mesh generation is still early/unreliable** — lean on curated marketplace assets first; treat
  text-to-3D as an experimental Phase 5+ lever.
- **Hardware** — Lumen/Nanite/crowds/MRQ are GPU-hungry; budget for a strong card or cloud render.
- **Licensing/IP** — disciplined provenance + originality; respect Fab/Megascans/MetaHuman/Unreal terms
  (and Unreal's royalty — see `playsmith unreal royalty`).
- **Scope discipline** — a *small, polished, real-looking* slice that ships beats an ambitious open
  world that doesn't. Prove one vertical (e.g. a photoreal third-person arena) before going wide.

---

*This roadmap layers on top of the current foundation (build-on-template, the director→critic refine
loop, theme palettes, the establishing-shot render, art generation). It is the "how we get to
next-gen" companion to [`docs/ROADMAP.md`](ROADMAP.md) (the near-term stage plan) and
[`CLAUDE.md`](../CLAUDE.md) (the source of truth).*
