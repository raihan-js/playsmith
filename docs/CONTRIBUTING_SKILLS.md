# Contributing a game-generation skill

Skills are the compounding moat (WHY.md): a growing, open library of genres Playsmith can build
well. This guide walks you through adding one. Read `docs/SKILL_SPEC.md` first — it's the
contract; this is the how-to.

## 1. Create the folder

```
game-skills/genres/<your-genre>/
├── SKILL.md
└── scripts/            # your deterministic templates (optional but strongly recommended)
```

Use a kebab-case name (e.g. `top-down`). It must match the `name:` in your frontmatter.
Playsmith targets **Unreal Engine 5.x**; the first UE genre skills (`third-person`,
`first-person`, `top-down`) are an emerging area being built in the upcoming stages, so they're
the natural starting points to contribute.

## 2. Write the frontmatter

```yaml
---
name: top-down
description: >
  Generate a top-down Unreal Engine 5.x game. Use when the user wants an overhead
  adventure, a top-down explorer, a twin-stick / isometric game, or any game where a
  character is controlled from above (not over-the-shoulder or first-person).
assertions:
  - player_exists
  - level_loads
  - no_errors
---
```

The **description** is what the router matches — write it the way users actually phrase the
request, including synonyms. Pick **assertions** from the vocabulary in `docs/SKILL_SPEC.md`
(add a new check to the harness in the same PR if your genre needs one).

## 3. Write the body

Follow the structure in `docs/SKILL_SPEC.md`: when-to-use, defaults, ordered build steps ending
in **RUN AND VERIFY**, an Unreal 5.x correctness checklist, bundled resources, common failure
modes, and a placeholder fallback. Keep it under ~500 lines. (The first UE genre skills land in
the upcoming stages; until then the spec is your reference for shape and tone.)

## 4. Bundle deterministic scaffolding

The single biggest reliability lever is giving the agent **correct scaffolding to copy** rather
than asking it to invent the hard parts. Add a `scripts/` template for the genre's core setup —
e.g. a UE Python automation script (`.py`) that places the player start, floor, goal, and
obstacles into the level, or build-on-template notes/refs for third-person / first-person /
top-down — and tell the agent in the body to use it and only tune constants. This is what makes a
7B local model succeed. (Scaffolding runs headless via `UnrealEditor-Cmd` and UE Python.)

## 5. Test routing

```bash
playsmith skills                 # your skill appears with its description
```

Confirm a representative prompt routes to your skill and that it does NOT steal prompts meant
for other skills. Add a routing assertion to `tests/test_skills.py` like the existing ones:

```python
def test_routes_to_top_down(...):
    router = SkillRouter(SkillLoader([game_skills_root]))
    assert router.route("an overhead twin-stick game seen from above").name == "top-down"
```

## 6. Prove it builds (when you can)

With Unreal Engine 5.x + a local model installed:

```bash
playsmith new "<a prompt for your genre>"
```

It should produce a runnable UE project whose declared assertions PASS. Record the result.

## 7. Open a PR

Include: the skill folder, any harness vocabulary additions (+ a `docs/SKILL_SPEC.md` update),
a routing test, and a one-line note on what you verified. Keep generated games out of the repo
(they belong in the user's `workspace_dir`).

## Checklist

- [ ] `name` is unique kebab-case and matches the folder.
- [ ] `description` covers the phrasings real users type.
- [ ] `assertions` are from the documented vocabulary (or you added one).
- [ ] Body has an explicit RUN AND VERIFY step.
- [ ] A `scripts/` template (e.g. a UE Python automation `.py`) carries the hard part deterministically.
- [ ] A routing test in `tests/test_skills.py`.
- [ ] Apache-2.0 compatible; original content, no copyrighted game IP/assets.
