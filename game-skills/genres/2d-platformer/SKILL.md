---
name: 2d-platformer
description: >
  Generate a complete, runnable 2D side-scrolling platformer game in Godot 4.
  Use this skill whenever the user wants a platformer, a jump-and-run game, a
  Mario-like or Celeste-like game, a "side-scroller," or any 2D game where a
  character runs, jumps across platforms, collects items, and avoids hazards —
  even if they don't say the word "platformer." Produces a real, editable Godot 4
  project (project.godot, .tscn scenes, .gd scripts), runs it to verify, and can
  export it. Prefer this skill over generic code generation for any 2D platformer request.
---

# 2D Platformer (Godot 4)

This skill builds a complete, **runnable** 2D platformer in **Godot 4.x** from a prompt,
then verifies it actually works by running it. It produces a real project the user can open
in the Godot editor and edit by hand.

> **Engine version:** Godot **4.x only.** The APIs below are 4.x and differ from 3.x.
> Never emit 3.x APIs (no `KinematicBody2D`, no `move_and_slide(velocity)` with arguments).

## When to use
Any request for a platformer / jump-and-run / side-scroller / "Mario-like" 2D game. If the
request is clearly 3D, top-down, puzzle, or another genre, defer to the matching skill.

## What the user gives you (and sensible defaults)
Extract from the prompt; fill gaps with defaults and state your assumptions:
- **Character** (default: a simple colored capsule placeholder, or a generated sprite if the
  asset pipeline is available).
- **Collectible** (default: coins) and **win condition** (default: reach the flag / collect all).
- **Hazard** (default: spikes — touching them resets the level or costs a life).
- **Vibe/theme** (drives asset prompts and palette; cosmetic, never blocks a runnable game).

## Build steps (the agent follows these in order)

1. **Scaffold the project.** Via the EngineAdapter: create the Godot 4 project (`project.godot`),
   set the main scene, define input actions if needed (default `ui_*` actions already exist).
2. **Player scene.** Create `Player.tscn`: a `CharacterBody2D` root with a `CollisionShape2D`
   and a `Sprite2D` (placeholder or generated). Attach `scripts/player.gd` (see bundled script).
3. **Player movement.** Use the bundled `scripts/player.gd` as the template — it implements
   run + gravity + jump correctly for Godot 4. Adjust `SPEED` / `JUMP_VELOCITY` to taste.
4. **Level.** Create `Main.tscn` with a `TileMapLayer` (or a few `StaticBody2D` platforms for
   the simplest version), place the player, add ground and a couple of platforms.
5. **Collectibles.** An `Area2D` `Coin.tscn` with a `body_entered` signal that frees itself and
   increments a score. Scatter several in the level.
6. **Hazard.** An `Area2D` `Spike.tscn` that, on `body_entered` by the player, reloads the
   current scene (`get_tree().reload_current_scene()`) or decrements a life.
7. **Win condition.** A `Goal` `Area2D` (flag) that, on `body_entered`, shows a simple win
   label or loads a "you win" screen.
8. **HUD.** A `CanvasLayer` with a `Label` showing score; update it from the coin signal.
9. **RUN AND VERIFY (do not skip).** Use the EngineAdapter to run the game (`run(headless=...)`),
   capture a `screenshot()` and `read_logs()`. If there are parse/runtime errors or the player
   falls through the floor / can't jump, **fix and re-run** until it works. A platformer is not
   "done" until the player visibly stands on ground and can jump in a screenshot, with no errors.
10. **Offer next steps.** Export (`export --target web`), generate themed sprites to replace
    placeholders, add enemies, add more levels, or publish.

## Godot 4 correctness checklist (enforce in all generated code)
- Player root is `CharacterBody2D` (NOT `KinematicBody2D`).
- `velocity` is a built-in property of `CharacterBody2D`; set it, then call `move_and_slide()`
  with **no arguments**.
- Use `is_on_floor()` to gate jumping.
- Read gravity from project settings:
  `var gravity := ProjectSettings.get_setting("physics/2d/default_gravity")`.
- Horizontal input: `Input.get_axis("ui_left", "ui_right")`.
- Jump input: `Input.is_action_just_pressed("ui_accept")`.
- Inspector-exposed tunables use `@export`.
- Scenes are text `.tscn`; scripts are `.gd`; entry config is `project.godot`.

## Bundled resources
- `scripts/player.gd` — a correct, ready-to-use Godot 4 player controller. Use it as the
  movement template; only adjust constants and the sprite reference. Read it before writing
  your own movement code.

## Common failure modes (and fixes)
- *Player falls through floor* → floor needs a `StaticBody2D`/`TileMapLayer` with a collision
  shape; player needs a `CollisionShape2D` with a real shape resource.
- *Can't jump* → jump must be gated by `is_on_floor()`, and `JUMP_VELOCITY` must be negative
  (Godot Y axis points down).
- *Parse error on `move_and_slide(velocity)`* → that's 3.x. In 4.x it takes no arguments.
- *Coin doesn't disappear* → connect the `Area2D.body_entered` signal and call `queue_free()`.

## If the asset pipeline is unavailable
Ship with placeholder shapes (a colored `ColorRect`/capsule sprite, simple rectangles for
platforms, small squares for coins). A runnable game with placeholders beats a pretty game
that doesn't run. Offer to generate themed art afterward.
