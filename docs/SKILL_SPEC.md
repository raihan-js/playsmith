# SKILL.md spec — game-generation skills

Playsmith skills use the open **SKILL.md** standard (interoperable with Claude Code / Codex /
Cursor — CLAUDE.md §8). A skill is a folder under `game-skills/genres/<name>/` that teaches the
agent how to build one genre of game well, with deterministic scaffolding it can lean on.

This spec is the contract a skill must satisfy. See `docs/CONTRIBUTING_SKILLS.md` for the
step-by-step on adding one. Playsmith targets **Unreal Engine 5.x**; the first UE genre skills
(`third-person`, `first-person`, `top-down`) are an emerging area being built in the upcoming
stages, so this spec is the reference until those land as worked examples.

## Folder layout

```
<skill-name>/
├── SKILL.md          # required: YAML frontmatter + markdown body
├── scripts/          # optional: deterministic code templates (e.g. a UE Python automation .py)
├── references/       # optional: engine API notes, loaded on demand
└── assets/           # optional: template art
```

## Frontmatter (required)

```yaml
---
name: third-person             # kebab-case, unique; matches the folder name
description: >                 # the "pushy" trigger text the router matches against
  One or two sentences that say exactly when to use this skill, including the synonyms a
  user might say (e.g. "over-the-shoulder", "3rd-person action", "behind-the-character") —
  even if they don't say the genre name. Be specific; this is what routing keys on.
assertions:                    # gameplay checks the reality loop must see PASS (see vocab below)
  - player_exists
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

The verify harness (`playsmith/engines/unreal/templates.py`) loads the level via UE Python under
`UnrealEditor-Cmd`, counts the key actors, and prints `PLAYSMITH_ASSERT key=value` lines a text
model can read — no display or vision model needed. Supported keys (the authoritative set lives in
`KNOWN_ASSERTIONS` in `playsmith/engines/base.py`):

| key | passes when |
|---|---|
| `level_loads` | the level loaded and produced actors (no load failure) |
| `no_errors` | no parse/runtime errors in the run logs (derived by the adapter) |
| `player_start_exists` | a `PlayerStart` actor exists in the level |
| `floor_exists` | at least one ground/floor mesh exists |
| `player_exists` | a player pawn/character exists in the level |
| `goal_exists` | a goal/objective actor (tagged) exists |
| `obstacles_exist` | one or more obstacle actors (tagged) exist |

`no_errors` applies to every genre. Movement/action genres use `player_exists` + `floor_exists`;
objective-driven levels add `goal_exists` / `obstacles_exist`. Need a new check? Add it to
`KNOWN_ASSERTIONS` and the UE harness in the same PR (and document it here). Richer
playability/quality gates (PIE metrics, rendered-screenshot scoring) are layered on by the
director/critic loop, not declared here.

## Body (required)

Markdown instructions, kept under ~500 lines:

1. **When to use** — restate the routing boundary.
2. **What the user gives you (and sensible defaults)** — how to fill gaps and state assumptions.
3. **Build steps** — an ordered plan the agent follows, ending in **RUN AND VERIFY**.
4. **RUN AND VERIFY (do not skip)** — call `run_engine`, then `verify_game`; fix until the
   declared assertions PASS. This is non-negotiable (CLAUDE.md §4).
5. **Unreal 5.x correctness checklist** — enforce current UE APIs in generated automation/code
   (build-on-template where it helps: third-person, first-person, top-down).
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
- runs with **no errors**, verified by its declared assertions (not just "it built");
- is a **real, editable** Unreal Engine 5.x project the user can open and change;
- degrades gracefully to **placeholders** when art generation is unavailable;
- is **routed to correctly** from the phrasings real users type.
