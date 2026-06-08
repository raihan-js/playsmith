---
name: endless-runner
description: >
  Generate a complete, runnable ENDLESS RUNNER in Godot 4. Use this skill whenever the user wants
  an endless runner, an "auto-runner", a "speeds up the longer you survive" game, a one-button
  jump-to-survive game, a Flappy-Bird/Chrome-dino/Subway-Surfers-like game, or any game where the
  world scrolls toward a fixed character that only JUMPS to avoid oncoming obstacles and is scored
  by distance. This is NOT a free-roaming platformer (the player does not walk left/right) and NOT
  a shooter. Produces a real, editable Godot 4 project, runs it to verify, and can export it.
assertions:
  - player_exists
  - player_on_floor
  - obstacle_spawns
  - no_errors
---

# Endless Runner (Godot 4)

A genuinely different game from the platformer: the runner stays at a **fixed x** and only falls
and jumps — **obstacles scroll toward it from the right**, faster and faster, and you score by
distance survived. One-button gameplay.

> **Engine version:** Godot **4.x only.** `CharacterBody2D` + gravity + `move_and_slide()` (no
> args), `Area2D` obstacles, text `.tscn` scenes.

## The shipped, working base (do NOT rewrite — embellish)
- `Main.tscn` — a `Node2D` with a `Background`, `Camera2D`, a ground `Floor` (StaticBody2D), the
  runner, and a HUD `Score`. Obstacles are spawned at runtime, not placed in the scene.
- `Player.tscn` / `scripts/player.gd` — a `CharacterBody2D` that applies gravity and jumps on
  `ui_accept` when `is_on_floor()`. No horizontal movement (the world moves, not the runner).
- `Obstacle.tscn` / `scripts/obstacle.gd` — an `Area2D` that scrolls left at the game's current
  `speed` and ends the run if it touches the player.
- `scripts/game.gd` — the director: spawns obstacles from the right edge on a timer, ramps `speed`
  over time, scores by `distance`, ends with a "Game Over" label, and applies generated art
  (`background.png`, `player.png`, `obstacle.png`) at runtime.

## How to personalize (small, safe edits only)
- Tune constants: `spawn_interval` (gap between obstacles), the speed ramp, `jump_velocity`.
- Add behaviour in GDScript (double-jump, variable obstacle heights, a coin pickup, a parallax
  layer) — never hand-write `.tscn`. Copy an existing node block if you must add a scene node.
- Art is auto-generated/applied: a themed `background`, a `player` runner sprite, an `obstacle`
  sprite. After EVERY change call `run_engine` + `verify_game`; keep
  `player_exists`, `player_on_floor`, `obstacle_spawns`, `no_errors` PASS. If a change breaks them,
  undo it; if you can't improve safely, call `task_complete`.

## Godot 4 correctness checklist
- Runner is a `CharacterBody2D`; gravity from `ProjectSettings.get_setting("physics/2d/default_gravity")`; jump gated by `is_on_floor()` with a NEGATIVE `jump_velocity`.
- Obstacles are `Area2D` in group `"obstacle"`, spawned with `load("res://Obstacle.tscn").instantiate()`; never placed in the scene.
- Use the project design resolution (`ProjectSettings` viewport size), not `get_viewport_rect()`.

## Common failure modes (and fixes)
- *No obstacles* → the spawn timer in `game.gd._physics_process` must call `_spawn_obstacle()`; obstacles join group `"obstacle"`.
- *Runner falls through floor* → the `Floor` needs a `StaticBody2D` + `CollisionShape2D`; the player needs a real `CollisionShape2D`.
- *Can't jump* → jump must be gated by `is_on_floor()` and `jump_velocity` must be negative.
