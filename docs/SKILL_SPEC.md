# SKILL.md spec — game-generation skills

Playsmith skills use the open **SKILL.md** standard (interoperable with Claude Code / Codex /
Cursor — CLAUDE.md §8). A skill is a folder under `game-skills/genres/<name>/` that teaches the
agent how to build one genre of game well, with deterministic scaffolding it can lean on.

This spec is the contract a skill must satisfy. See `docs/CONTRIBUTING_SKILLS.md` for the
step-by-step on adding one, and the two reference skills: `2d-platformer` and `visual-novel`.

## Folder layout

```
<skill-name>/
├── SKILL.md          # required: YAML frontmatter + markdown body
├── scripts/          # optional: deterministic code templates (e.g. player.gd, dialogue.gd)
├── references/       # optional: engine API notes, loaded on demand
└── assets/           # optional: template art
```

## Frontmatter (required)

```yaml
---
name: 2d-platformer            # kebab-case, unique; matches the folder name
description: >                 # the "pushy" trigger text the router matches against
  One or two sentences that say exactly when to use this skill, including the synonyms a
  user might say (e.g. "jump-and-run", "Mario-like", "side-scroller") — even if they don't
  say the genre name. Be specific; this is what routing keys on.
assertions:                    # gameplay checks the reality loop must see PASS (see vocab below)
  - player_on_floor
  - no_errors
---
```

- **name** — kebab-case, unique, equals the folder name.
- **description** — the single most important field for routing. Write it "pushy": list the
  words and phrasings a user would actually type. The router matches a prompt to a skill by
  this text (LLM-based, with a keyword fallback).
- **assertions** — the genre's checks for the **assertion-based reality loop** (CLAUDE.md §4).
  The agent (and the final authoritative verification) only call a build "done" when every
  listed assertion PASSES, headless. Pick from the vocabulary below.

## Assertion vocabulary (what the in-engine harness can check, headless)

The verify harness (`playsmith/engines/godot/templates.py`) instances the main scene, runs
~90 physics frames, and prints `PLAYSMITH_ASSERT key=value`. Supported keys:

| key | passes when |
|---|---|
| `scene_loads` | the main scene instantiated and produced nodes (no load failure) |
| `no_errors` | no parse/runtime errors in the run logs (derived by the adapter) |
| `player_exists` | a `CharacterBody2D` exists in the scene |
| `player_on_floor` | that body reports `is_on_floor()` after physics settles |
| `player_not_falling` | the body did not fall far below its start (didn't drop through the floor) |
| `has_dialogue_ui` | a `Label`, `RichTextLabel`, or `Button` exists (a text/UI game) |

`no_errors` applies to every genre. Platformers use the `player_*` checks; story/UI games use
`scene_loads` + `has_dialogue_ui`. Need a new check? Add it to the harness vocabulary in the
same PR (and document it here).

## Body (required)

Markdown instructions, kept under ~500 lines. Mirror the two reference skills:

1. **When to use** — restate the routing boundary.
2. **What the user gives you (and sensible defaults)** — how to fill gaps and state assumptions.
3. **Build steps** — an ordered plan the agent follows, ending in **RUN AND VERIFY**.
4. **RUN AND VERIFY (do not skip)** — call `run_engine`, then `verify_game`; fix until the
   declared assertions PASS. This is non-negotiable (CLAUDE.md §4).
5. **Godot 4 correctness checklist** — enforce 4.x APIs in generated code.
6. **Bundled resources** — point at `scripts/` templates and say to read them first.
7. **Common failure modes (and fixes)** — the genre's usual bugs and their fixes.
8. **If the asset pipeline is unavailable** — placeholders always work; art is an upgrade.

## Progressive disclosure (how skills are loaded)

1. **Metadata** (name + description + assertions) — always loaded, tiny; used for routing.
2. **Body** — loaded only once the skill is selected.
3. **Bundled resources** (`scripts/`, `references/`) — paths are exposed, contents read only
   when a step needs them.

Keep the body lean and push detail into `references/` so routing stays cheap.

## Quality bar for a skill

A skill is good when, from a one-line prompt, it produces a project that:
- runs with **no errors**, verified by its declared assertions (not just "it compiled");
- is a **real, editable** Godot 4 project the user can open and change;
- degrades gracefully to **placeholders** when art generation is unavailable;
- is **routed to correctly** from the phrasings real users type.
