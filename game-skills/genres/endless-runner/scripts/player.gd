# player.gd — endless-runner avatar (Godot 4.x). The world scrolls past a fixed runner: it only
# falls and jumps. Obstacles come to it. No horizontal input.
extends CharacterBody2D

@export var jump_velocity: float = -560.0

var gravity: float = ProjectSettings.get_setting("physics/2d/default_gravity")


func _ready() -> void:
	add_to_group("player")


func _physics_process(delta: float) -> void:
	if not is_on_floor():
		velocity.y += gravity * delta
	if Input.is_action_just_pressed("ui_accept") and is_on_floor():
		velocity.y = jump_velocity
	velocity.x = 0.0
	move_and_slide()
