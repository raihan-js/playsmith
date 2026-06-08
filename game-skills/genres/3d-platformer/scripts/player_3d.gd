# player_3d.gd — Godot 4.x player controller template (3D platformer).
# Attach to a CharacterBody3D that has a CollisionShape3D and a MeshInstance3D child
# (and usually a Camera3D). This is the movement template referenced by SKILL.md. Adjust the
# constants; the structure is correct for Godot 4 3D and should NOT be ported to 2D or 3.x.
#
# Note: in 3D, +Y points UP (opposite of 2D), so gravity is SUBTRACTED and jump_velocity is positive.

extends CharacterBody3D

@export var speed: float = 5.0
@export var jump_velocity: float = 4.5

# Pull the project's default 3D gravity so physics matches the editor settings.
var gravity: float = ProjectSettings.get_setting("physics/3d/default_gravity")


func _physics_process(delta: float) -> void:
	# Apply gravity while airborne (+Y is up in 3D, so subtract).
	if not is_on_floor():
		velocity.y -= gravity * delta

	# Jump only when standing on the floor.
	if Input.is_action_just_pressed("ui_accept") and is_on_floor():
		velocity.y = jump_velocity

	# Movement on the XZ plane from arrow keys / left stick (ui_* actions exist by default).
	var input_dir := Input.get_vector("ui_left", "ui_right", "ui_up", "ui_down")
	var direction := (transform.basis * Vector3(input_dir.x, 0.0, input_dir.y)).normalized()
	if direction != Vector3.ZERO:
		velocity.x = direction.x * speed
		velocity.z = direction.z * speed
	else:
		velocity.x = move_toward(velocity.x, 0.0, speed)
		velocity.z = move_toward(velocity.z, 0.0, speed)

	# Godot 4: set `velocity`, then call move_and_slide() with NO arguments.
	move_and_slide()
