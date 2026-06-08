---
name: 3d-platformer
description: >
  Generate a basic, runnable 3D platformer game in Godot 4. Use this skill whenever the user
  wants a three-dimensional platformer, a 3D jump-and-collect game, a third-person character
  that runs and jumps around a 3D level, a "3D Mario-like," a low-poly collectathon, or any
  game explicitly set in 3D / three dimensions (a robot collecting orbs, a character exploring
  a 3D world). Choose this over the 2d-platformer skill ONLY when the request is clearly 3D /
  three-dimensional / third-person. Produces a real, editable Godot 4 project (project.godot,
  .tscn scenes, .gd scripts) with a CharacterBody3D player, runs it to verify, and can export it.
assertions:
  - player_exists
  - player_on_floor
  - no_errors
---

# 3D Platformer (Godot 4)

This skill builds a basic but **runnable** 3D platformer in **Godot 4.x** from a prompt, then
verifies it actually works by running it. It produces a real project the user can open in the
Godot editor and edit by hand.

> **Scope:** "basic but runnable" — a player that stands on a floor, moves on the XZ plane, and
> jumps; a collectible; a camera and a light. Not an open world. Keep it small and correct.
> **Engine version:** Godot **4.x only.** In 3D, **+Y points UP** (opposite of 2D), so gravity is
> subtracted and `jump_velocity` is positive. Never emit 3.x APIs.

## When to use
A request that is clearly **3D / three-dimensional / third-person** platforming. If the request
is 2D / side-scrolling, defer to `2d-platformer`. If it's a story/dialogue game, defer to
`visual-novel`.

## What the user gives you (and sensible defaults)
- **Character** (default: a capsule `MeshInstance3D` placeholder, or a generated mesh if the 3D
  asset pipeline is available).
- **Collectible** (default: floating coins/orbs) and **win condition** (default: collect all).
- **Vibe/theme** (drives mesh/material prompts and palette; cosmetic, never blocks a runnable game).

## Build steps (the agent follows these in order)
1. **Scaffold the project.** `project.godot` and `Main.tscn` (a `Node3D`) already exist; build the
   level inside `Main.tscn`. Uses the GL Compatibility renderer (good for low-end + web).
2. **Floor.** Add a `StaticBody3D` with a `CollisionShape3D` (a `BoxShape3D`, e.g. 20×1×20) and a
   matching `MeshInstance3D` (`BoxMesh`) so the player has ground to stand on.
3. **Player scene.** A `CharacterBody3D` root with a `CollisionShape3D` (a `CapsuleShape3D`), a
   `MeshInstance3D` (`CapsuleMesh` placeholder or generated mesh), and a `Camera3D` positioned
   behind/above. Attach the bundled `scripts/player_3d.gd`. Place the player above the floor.
4. **Player movement.** Use the bundled `scripts/player_3d.gd` as the template — it implements
   run + gravity + jump correctly for Godot 4 3D. Adjust `speed` / `jump_velocity` to taste.
5. **Light + environment.** Add a `DirectionalLight3D` (and optionally a `WorldEnvironment`) so
   the scene is lit and visible.
6. **Collectibles.** An `Area3D` `Coin.tscn` with a `body_entered` signal that frees itself and
   increments a score. Scatter several above the floor.
7. **RUN AND VERIFY (do not skip).** Run the game (`run_engine`), then call `verify_game` and
   confirm the assertions PASS: `player_exists`, `player_on_floor`, `no_errors`. If the player
   falls through the floor (no collision shape) or there are parse/runtime errors, **fix and
   re-verify** until it works. A 3D platformer is not "done" until the player stands on the floor
   with no errors.
8. **Offer next steps.** Export (`export --target web`), generate themed meshes/materials to
   replace placeholders, add enemies/levels, or publish.

## Godot 4 3D correctness checklist (enforce in all generated code)
- Player root is `CharacterBody3D` (NOT `KinematicBody`).
- `velocity` is a built-in property; set it, then call `move_and_slide()` with **no arguments**.
- +Y is UP: apply gravity with `velocity.y -= gravity * delta`; `jump_velocity` is **positive**.
- Read gravity from `ProjectSettings.get_setting("physics/3d/default_gravity")`.
- Movement on XZ: `Input.get_vector("ui_left", "ui_right", "ui_up", "ui_down")`.
- Floor needs a `StaticBody3D` + `CollisionShape3D`; player needs a `CollisionShape3D` with a real shape.
- Scene needs a `Camera3D` and a `DirectionalLight3D` to be visible.

## Bundled resources
- `scripts/player_3d.gd` — a correct, ready-to-use Godot 4 3D player controller. Use it as the
  movement template; only adjust constants and the mesh. Read it before writing your own movement.

## Common failure modes (and fixes)
- *Player falls forever* → the floor needs a `StaticBody3D` with a `CollisionShape3D`; the player
  needs a `CollisionShape3D` with a real `CapsuleShape3D`/`BoxShape3D`.
- *Can't jump / floats* → gravity must be SUBTRACTED in 3D and gated by `is_on_floor()`;
  `jump_velocity` must be positive.
- *Black screen* → add a `Camera3D` and a `DirectionalLight3D`; ensure the camera looks at the player.
- *Parse error on `move_and_slide(velocity)`* → in 4.x it takes no arguments.

## If the asset pipeline is unavailable
Ship with placeholder meshes (`CapsuleMesh` player, `BoxMesh` floor/platforms, small spheres for
coins). A runnable 3D game with primitives beats a pretty one that doesn't run. Note clearly that
AI-generated 3D meshes usually need cleanup (topology/UVs) before they're game-ready.
