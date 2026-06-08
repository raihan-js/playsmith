extends CharacterBody2D

@export var speed: float = 220.0
@export var jump_velocity: float = -420.0

var gravity: float = ProjectSettings.get_setting("physics/2d/default_gravity")

func _physics_process(delta: float) -> void:
	if not is_on_floor():
		velocity.y += gravity * delta

	if Input.is_action_just_pressed("ui_accept") and is_on_floor():
		velocity.y = jump_velocity

	var direction: float = Input.get_axis("ui_left", "ui_right")
	if direction != 0.0:
		velocity.x = direction * speed
		var sprite := get_node_or_null("Sprite2D")
		if sprite:
			sprite.flip_h = direction < 0.0
	else:
		velocity.x = move_toward(velocity.x, 0.0, speed)

	move_and_slide()