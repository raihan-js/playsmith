---
name: space-shooter
description: >
  Generate a complete, runnable top-down SPACE SHOOTER (shoot-'em-up / shmup) in Godot 4.
  Use this skill whenever the user wants a space shooter, a shmup, "shoot enemy ships",
  "dodge asteroids and blast", a Galaga/1942/Space-Invaders-like game, a top-down arcade
  shooter, or any game where a player ship MOVES, FIRES projectiles, and waves of enemies
  spawn and descend. NOT a platformer (no gravity, no jumping, no floor). Produces a real,
  editable Godot 4 project (project.godot, .tscn scenes, .gd scripts), runs it to verify,
  and can export it. Prefer this skill over generic code generation for any shooter request.
assertions:
  - player_exists
  - enemy_spawns
  - no_errors
---

# Space Shooter (Godot 4)

This skill builds a complete, **runnable** top-down shoot-'em-up in **Godot 4.x**. It is a
genuinely different game from the platformer: **no gravity, no platforms, no floor** — a ship
flies in open space, fires upward, and survives waves of descending enemies.

> **Engine version:** Godot **4.x only.** Use `Input.get_vector(...)`, `Area2D` signals,
> `move_and_slide()` with no arguments, `@export` vars, text `.tscn` scenes.

## The shipped, working base (do NOT rewrite — embellish)
A complete playable game is scaffolded for you:
- `Main.tscn` — a `Node2D` with a `Background`, a `Camera2D`, the player ship, and a HUD
  (`Score` + `Lives`). Enemies and bullets are spawned at runtime, not placed in the scene.
- `Player.tscn` — a `CharacterBody2D` ship (`scripts/player.gd`): 8-direction movement clamped
  to the screen, fires `Bullet.tscn` on `ui_accept` with a cooldown.
- `Enemy.tscn` / `scripts/enemy.gd` — an `Area2D` enemy that descends; a bullet destroys it
  (+score), and it costs a life if it reaches the bottom or touches the player.
- `Bullet.tscn` / `scripts/bullet.gd` — an `Area2D` projectile travelling up that frees the
  first enemy it overlaps.
- `scripts/game.gd` — the director: spawns enemies on a timer at random x, tracks score/lives,
  ends at 0 lives, and applies generated art (`background.png`, `player.png`/ship,
  `enemy.png`) at runtime.

## How to personalize (small, safe edits only)
- Tune constants: `spawn_interval` (wave pace), enemy `speed`, player `speed`/`fire_cooldown`.
- Add behaviour in GDScript (e.g. enemy zig-zag, a second enemy type, power-ups) — never by
  hand-writing `.tscn`. Copy an existing node block if you must add a scene node.
- Art is auto-generated and applied: a themed `background`, a `player` ship sprite, and an
  `enemy` sprite. Generating a `bullet.png` is also picked up automatically.
- After EVERY change call `run_engine` + `verify_game`. The assertions
  (`player_exists`, `enemy_spawns`, `no_errors`) must stay PASS. If a change breaks them, undo
  it. If you can't improve it safely, call `task_complete` — the base game is good.

## Godot 4 correctness checklist
- Player ship is a `CharacterBody2D`; movement via `Input.get_vector("ui_left","ui_right","ui_up","ui_down")`, then `move_and_slide()` (no args).
- Enemies/bullets are `Area2D`; connect `area_entered` / `body_entered` in code.
- Spawn with `load("res://Enemy.tscn").instantiate()` + `add_child(...)`; never place waves in the scene.
- Scenes are text `.tscn`; scripts `.gd`; entry config `project.godot`.

## Common failure modes (and fixes)
- *No enemies appear* → the spawn timer in `game.gd._process` must call `_spawn_enemy()`; enemies join group `"enemy"`.
- *Bullets don't hit* → bullet `area_entered` checks `area.is_in_group("enemy")` and calls `area.hit()`.
- *Ship flies off screen* → clamp `global_position` to the viewport in `player.gd`.
