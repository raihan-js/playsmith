# player.gd — top-down ship controller (space-shooter). Godot 4.x only.
# Moves in 8 directions, clamps to the screen, and fires bullets on a cooldown.
extends CharacterBody2D

@export var speed: float = 360.0
@export var fire_cooldown: float = 0.26

var _cooldown: float = 0.0
var _view: Vector2 = Vector2(1152, 648)


func _ready() -> void:
	add_to_group("player")
	_view = Vector2(
		float(ProjectSettings.get_setting("display/window/size/viewport_width", 1152)),
		float(ProjectSettings.get_setting("display/window/size/viewport_height", 648)),
	)


func _physics_process(delta: float) -> void:
	var dir := Input.get_vector("ui_left", "ui_right", "ui_up", "ui_down")
	velocity = dir * speed
	move_and_slide()
	global_position.x = clamp(global_position.x, 24.0, _view.x - 24.0)
	global_position.y = clamp(global_position.y, 24.0, _view.y - 24.0)

	_cooldown -= delta
	if Input.is_action_pressed("ui_accept") and _cooldown <= 0.0:
		_fire()
		_cooldown = fire_cooldown


func _fire() -> void:
	var scene: PackedScene = load("res://Bullet.tscn")
	if scene == null:
		return
	var bullet: Node = scene.instantiate()
	get_parent().add_child(bullet)
	bullet.global_position = global_position + Vector2(0, -34)
	if ResourceLoader.exists("res://assets/bullet.png"):
		var spr = bullet.get_node_or_null("Sprite2D")
		if spr and spr is Sprite2D:
			spr.texture = load("res://assets/bullet.png")
