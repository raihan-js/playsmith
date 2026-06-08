# player.gd — Godot 4.x player controller template (2D platformer)
# Attach to a CharacterBody2D that has a CollisionShape2D and a Sprite2D child.
# This is the movement template referenced by SKILL.md. Adjust the constants and
# the sprite as needed; the structure is correct for Godot 4 and should not be ported to 3.x.

extends CharacterBody2D

@export var speed: float = 220.0
@export var jump_velocity: float = -420.0   # negative because +Y points DOWN in Godot

# Pull the project's default gravity so physics feels consistent with the editor settings.
var gravity: float = ProjectSettings.get_setting("physics/2d/default_gravity")


func _physics_process(delta: float) -> void:
	# Apply gravity while airborne.
	if not is_on_floor():
		velocity.y += gravity * delta

	# Jump only when standing on the floor.
	if Input.is_action_just_pressed("ui_accept") and is_on_floor():
		velocity.y = jump_velocity

	# Horizontal movement from arrow keys / left stick (ui_left / ui_right exist by default).
	var direction: float = Input.get_axis("ui_left", "ui_right")
	if direction != 0.0:
		velocity.x = direction * speed
		# Flip the sprite to face movement direction (assumes a child node named "Sprite2D").
		var sprite := get_node_or_null("Sprite2D")
		if sprite:
			sprite.flip_h = direction < 0.0
	else:
		# Decelerate smoothly to a stop.
		velocity.x = move_toward(velocity.x, 0.0, speed)

	# Godot 4: set `velocity`, then call move_and_slide() with NO arguments.
	move_and_slide()
