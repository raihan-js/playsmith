---
name: visual-novel
description: >
  Generate a complete, runnable 2D dialogue / visual-novel "story" game in Godot 4.
  Use this skill whenever the user wants a story game, a branching narrative, a
  dialogue-driven game, an interactive fiction, a "choose your own adventure," a
  detective/mystery story, a kinetic novel, or any game that is mostly about reading
  text, talking to characters, and making choices that branch — even if they don't
  say "visual novel." Produces a real, editable Godot 4 project (project.godot, .tscn
  scenes, .gd scripts) with a typed dialogue box and choice buttons, runs it to verify,
  and can export it. Prefer this skill over the 2d-platformer skill for any story- or
  dialogue-first game (no jumping/running gameplay).
assertions:
  - scene_loads
  - has_dialogue_ui
  - no_errors
---

# Visual Novel / Story (Godot 4)

This skill builds a complete, **runnable** dialogue/branching-story game in **Godot 4.x** from a
prompt, then verifies it actually works by running it. It produces a real project the user can
open in the Godot editor and edit by hand.

> **Engine version:** Godot **4.x only.** Scenes are text `.tscn` (format=3), scripts are `.gd`,
> config is `project.godot` (config_version=5). Never emit 3.x APIs.

## When to use
Any request for a story / narrative / dialogue / interactive-fiction / "choose your own
adventure" / mystery game where the core loop is *reading text and making choices*, not
platforming. If the request is clearly a platformer, action, puzzle, or other gameplay genre,
defer to the matching skill.

## What the user gives you (and sensible defaults)
Extract from the prompt; fill gaps with defaults and state your assumptions:
- **Setting / theme** (e.g. a lighthouse keeper, a detective in a rainy city) — drives the
  background art prompt and the writing.
- **Characters** (default: a narrator + one speaker).
- **A branch** (default: at least one choice that leads to two different short endings).
- **Art** (default: a colored `ColorRect` background and placeholder portraits, or imported/
  generated art if available — cosmetic, never blocks a runnable game).

## Build steps (the agent follows these in order)
1. **Scaffold the project.** Via the EngineAdapter: the Godot 4 project (`project.godot`) and
   `Main.tscn` as the main scene already exist; build the story inside `Main.tscn`.
2. **Dialogue UI.** In `Main.tscn`, under a root with a background `ColorRect` (full-rect),
   add a `CanvasLayer` containing: a `RichTextLabel` named **"Text"** (the line), a `Label`
   named **"Speaker"** (who is talking), and a `VBoxContainer` named **"Choices"** (for choice
   buttons). Anchor them to the bottom of the screen like a dialogue box.
3. **Dialogue controller.** Attach the bundled `scripts/dialogue.gd` to the `CanvasLayer`
   (see bundled script). Fill its `lines` array with the story (each entry `"Speaker: text"`).
4. **Branching.** Populate the controller's `branches` dictionary: at the choice point, map the
   line index to a couple of `{text, goto}` choices that jump to different lines/endings.
5. **Backgrounds / portraits.** Use placeholder `ColorRect`s or a `Sprite2D` with imported/
   generated art for the background and (optionally) a character portrait.
6. **RUN AND VERIFY (do not skip).** Use the EngineAdapter to run the game (`run_engine`), then
   call `verify_game` and confirm the assertions PASS: `scene_loads`, `has_dialogue_ui`,
   `no_errors`. If the scene fails to load, the dialogue box is missing, or there are parse/
   runtime errors, **fix and re-verify** until it works. A story game is not "done" until the
   dialogue UI is present and the scene runs with no errors.
7. **Offer next steps.** Export (`export --target web`), generate themed backgrounds/portraits
   to replace placeholders, add more branches/characters, or publish.

## Godot 4 correctness checklist (enforce in all generated code)
- Dialogue UI lives under a `CanvasLayer`; the line uses a `RichTextLabel`, choices are
  `Button`s added to a `VBoxContainer`.
- Advance the dialogue on `Input.is_action_just_pressed("ui_accept")` (handled in the template).
- Connect a `Button.pressed` signal (Godot 4 `Callable` syntax: `button.pressed.connect(...)`).
- Scenes are text `.tscn` (format=3); scripts are `.gd`; entry config is `project.godot`.

## Bundled resources
- `scripts/dialogue.gd` — a correct, ready-to-use Godot 4 dialogue controller (linear lines +
  optional `branches`). Use it as the template; fill `lines`/`branches`, only adjust structure
  if needed. Read it before writing your own dialogue code.

## Common failure modes (and fixes)
- *Nothing shows on screen* → the `RichTextLabel` must be named "Text" and added under the
  `CanvasLayer` the script is attached to; the script sets `_text.text` in `_ready`.
- *Choices don't branch* → populate `branches[index]` with `{text, goto}` entries; the template
  renders Buttons and wires `goto`.
- *Parse error on signal connect* → use Godot 4 `button.pressed.connect(callable)`, not the 3.x
  `connect("pressed", self, "method")`.

## If the asset pipeline is unavailable
Ship with placeholder shapes (a colored `ColorRect` background, simple rectangles/placeholder
textures for portraits). A runnable story game with placeholders beats a pretty one that
doesn't run. Offer to generate themed art afterward.
